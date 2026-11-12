"""Qualified fast RPCs keep snapshot identity and commit failure semantics."""
import contextlib,json,struct,subprocess,sys,unittest,zlib
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from keyboard_bluetooth import BluetoothKeyboard,snapshot_crc,unpack_snapshot
from test_bluetooth_host import fixture


def packed(data,capacity=248,codec=1):
 out=bytearray();at=0
 while at<len(data) and len(out)+2<=capacity:
  if codec==2 and data[at]==0 and len(out)+3<=capacity:
   zeros=1
   while at+zeros<len(data) and data[at+zeros]==0:zeros+=1
   if zeros>256:out.extend(b'\x80'+struct.pack('<H',zeros));at+=zeros;continue
  count=1
  while count<128 and at+count<len(data) and data[at+count]==data[at]:count+=1
  out.extend((0 if codec==2 and count==1 else 128| (count-1),data[at]));at+=count
 return at,bytes(out)


class FastBluetoothTest(unittest.TestCase):
 def setUp(self):
  self.live=fixture();self.calls=[];self.snapshots={};self.version=1;self.codec=1;self.corrupt=False;self.lost=False;self.save_failed=False;self.legacy_phase=0
  self.mocks=[patch('keyboard_bluetooth.TransportLock',side_effect=lambda _:contextlib.nullcontext()),patch('keyboard_bluetooth.subprocess.run',side_effect=self.helper)]
  for m in self.mocks:m.start()
 def tearDown(self):
  for m in reversed(self.mocks):m.stop()
 def helper(self,args,**kwargs):
  if args==['probe','--check']:return subprocess.CompletedProcess(args,0,json.dumps(dict(access='granted',fast_settings_version=self.version,fast_snapshot_codec=self.codec)),'')
  q=bytes.fromhex(kwargs['input']);nonce=q[:4];payload=b'';status=phase=0
  if '--fast-settings-request' in args:
   command=q[4];offset=struct.unpack_from('<H',q,5)[0];body=q[7:];self.calls.append((command,offset,body))
   if command==9:
    if not offset:self.snapshots[nonce]=self.live
    codec=2 if body==b'\2' else 1
    source=self.snapshots[nonce];count,tokens=packed(source[offset:],codec=codec);phase=0 if offset+count==len(source) else 2
    payload=bytes([codec,7])+struct.pack('<IH',snapshot_crc(source),count)+tokens
   elif command==10:
    if struct.unpack_from('<I',body)[0]!=snapshot_crc(self.live):status=2
    else:
     value=bytearray(self.live);at=4
     while at<len(body):
      position,count=struct.unpack_from('<HB',body,at);at+=3;value[position:position+count]=body[at:at+count];at+=count
     struct.pack_into('<I',value,156,zlib.crc32(value[:156]));struct.pack_into('<I',value,len(value)-4,zlib.crc32(value[160:-4]));self.live=bytes(value)
     phase=5 if offset else 4
     if offset and self.save_failed:status=5;phase=7
     else:payload=struct.pack('<I',snapshot_crc(self.live))
  else:
   _,command,offset,_=struct.unpack_from('<IBHH',q,4);self.calls.append((command,offset,b''))
   if command==0:payload=struct.pack('<BHHB',3,3232,256,48)
   elif command==6:payload=b'\7'
   elif command==1:payload=struct.pack('<I',snapshot_crc(self.live));phase=2
   elif command==5:phase=0
  r=nonce+struct.pack('<BBBHH',command,status,phase,offset,len(payload))+payload;r+=struct.pack('<I',zlib.crc32(r)^self.corrupt)
  good=not(self.lost and command==10)
  return subprocess.CompletedProcess(args,0 if good else 1,json.dumps(dict(access='granted',settings_reply_verified=good,settings_response_hex=r.hex())),'')
 def desired(self):
  data=bytearray(self.live);data[119]=1;struct.pack_into('<I',data,156,zlib.crc32(data[:156]));return bytes(data)
 def test_qualified_read_avoids_legacy_handshake_and_releases_snapshot(self):
  with BluetoothKeyboard('probe',fast=True) as k:self.assertEqual(k.read(),self.live);self.assertFalse(k.session)
  self.assertTrue(all(x[0]==9 for x in self.calls));self.assertLess(len(self.calls),5)
 def test_atomic_change_and_crc_verification_need_one_rpc(self):
  baseline=self.live;wanted=self.desired()
  with BluetoothKeyboard('probe',fast=True) as k:
   self.assertTrue(k.apply(wanted,baseline=baseline)['applied']);self.assertEqual(k.verify(wanted),wanted)
  self.assertEqual(self.live,wanted);self.assertEqual(len(self.calls),1);self.assertEqual(self.calls[0][0],10);self.assertEqual(len(self.calls[0][2]),8)
 def test_save_is_explicit_and_failure_is_not_retried(self):
  self.save_failed=True
  with BluetoothKeyboard('probe',fast=True) as k:
   with self.assertRaisesRegex(RuntimeError,'Save failed'):k.apply(self.desired(),save=True,baseline=self.live)
  self.assertEqual([c[:2] for c in self.calls],[(10,1)])
 def test_lost_commit_has_no_retry_or_snapshot_fallback(self):
  self.lost=True
  with BluetoothKeyboard('probe',fast=True) as k:
   with self.assertRaises(RuntimeError):k.apply(self.desired(),baseline=self.live)
  self.assertEqual([c[0] for c in self.calls],[10])
 def test_stale_baseline_does_not_apply(self):
  baseline=self.live;self.live=self.desired()
  with BluetoothKeyboard('probe',fast=True) as k:
   with self.assertRaisesRegex(RuntimeError,'CRC'):k.apply(baseline,baseline=baseline)
  self.assertEqual([c[0] for c in self.calls],[10])
 def test_absent_qualification_uses_explicit_legacy_contract(self):
  self.version=0
  with BluetoothKeyboard('probe',fast=True) as k:self.assertFalse(k.fast_mode)
  self.assertEqual([c[0] for c in self.calls],[0,6])
 def test_corrupt_read_fails_without_another_read(self):
  self.corrupt=True
  with BluetoothKeyboard('probe',fast=True) as k:
   with self.assertRaisesRegex(RuntimeError,'CRC'):k.read()
  self.assertEqual([c[0] for c in self.calls if c[0]==9],[9])
  self.assertEqual([c[0] for c in self.calls],[9])
 def test_compact_codec_is_explicit_and_keeps_snapshot_identity(self):
  self.codec=2
  with BluetoothKeyboard('probe',fast=True) as k:self.assertEqual(k.read(),self.live)
  self.assertTrue(all(c[2]==b'\2' for c in self.calls));self.assertEqual(len(self.snapshots),1)
 def test_compact_zero_span_bounds_and_legacy_token_are_distinct(self):
  self.assertEqual(unpack_snapshot(b'\x80\x00\x0c',3072,2),bytes(3072))
  self.assertEqual(unpack_snapshot(b'\x80\x00',1),b'\0')
  for value,expected in [(b'\x80',1),(b'\x80\0',1),(b'\x80\0\0',1),(b'\x80\2\0',1)]:
   with self.assertRaises(RuntimeError):unpack_snapshot(value,expected,2)
 def test_unknown_codec_fails_before_any_wire_request(self):
  self.codec=3
  with self.assertRaisesRegex(RuntimeError,'codec'):
   with BluetoothKeyboard('probe',fast=True):pass
  self.assertEqual(self.calls,[])
 def test_dense_snapshot_uses_same_nonce_and_ordered_offsets(self):
  data=bytearray(self.live)
  for i in range(168,len(data)-4):data[i]=i*73%256
  struct.pack_into('<I',data,len(data)-4,zlib.crc32(data[160:-4]));self.live=bytes(data)
  with BluetoothKeyboard('probe',fast=True) as k:self.assertEqual(k.read(),self.live)
  offsets=[c[1] for c in self.calls];self.assertGreater(len(offsets),2);self.assertEqual(offsets,sorted(set(offsets)));self.assertEqual(len(self.snapshots),1)

if __name__=='__main__':unittest.main()
