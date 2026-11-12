#!/usr/bin/env python3
"""Exact ARM fast carrier, atomic Apply/Save and priority/CRC regressions."""
import argparse,ctypes,hashlib,json,struct,zlib
from pathlib import Path
from keyboard_customize import BUNDLE_BYTES,validate
from keyboard_bluetooth import snapshot_crc,unpack_snapshot
from system_emulator import HOST,System
from test_bluetooth_settings_system import ReplyState


def fast_symbols(command,nonce,offset=0,body=b'',corrupt=False):
 data=bytes([5,command,6+len(body)])+nonce+struct.pack('<H',offset)+body
 data+=struct.pack('<I',zlib.crc32(data)^corrupt)
 previous=27
 yield 0;yield previous
 for byte in data:
  for shift in (4,0):
   digit=(byte>>shift)&15;previous=digit+1 if previous==27 else (previous+digit)%26+1
   assert 1<=previous<=26 and previous>>2!=7
   yield previous


def run(image):
 with System(image) as m:
  m.until('housekeeping_task_user')
  def step(ms=2):
   for elapsed in range(0,ms,2):
    m.write32(HOST+0x30,0);m.advance(min(2,ms-elapsed));m.pump()
    if m.read(m.symbols['waiting'],1)==b'\1':
     for byte in b'\x61\x0d\x0a':m.write32(HOST+0x44,byte)
     m.advance(1);m.pump()
  def inject(data):
   for byte in data:m.write32(HOST+0x44,byte)
   step()
  def trace():return m.read(0x61000000,m.read32(HOST+0x40))
  step(100);m.write32(HOST+0x200,(1<<10)|(1<<2)|(1<<3));m.write32(HOST+0x204,0)
  step(100);inject(b'\x5b\x32\x8d');step(100)
  assert m.read(m.symbols['active_slot'],1)==b'\1'
  nonce=0x79130201
  def rpc(command,offset=0,body=b'',token=None):
   nonlocal nonce
   nonce+=1;prefix=struct.pack('<I',nonce if token is None else token);before=len(trace())
   for symbol in fast_symbols(command,prefix,offset,body):
    value=(symbol<<3)|2;inject(bytes([0x5a,value,(0x5a+value)&255]))
   for _ in range(400):
    step(10)
    if m.read(m.symbols['bluetooth_settings']+ReplyState.replying.offset,1)==b'\0':break
   step(10);raw=trace()[before:];values=[];packets=[];at=0
   while at+10<=len(raw):
    p=raw[at:at+10]
    if p[0]==0xa1 and sum(p[:-1])&255==p[-1]:
     assert p[8]==0;packets.append(p);values.append(p[2]);at+=10
    else:at+=1
   assert 255 in values,(command,values[:8]);values=values[values.index(255)+1:];decoded=bytearray();bits=value=groups=0;previous=255
   for symbol in values:
    if symbol==previous:continue
    previous=symbol
    if len(decoded)>=11 and len(decoded)==15+struct.unpack_from('<H',decoded,9)[0]:break
    assert symbol>>7==groups%2;groups+=1;value|=(symbol&127)<<bits;bits+=7
    while bits>=8:decoded.append(value&255);value>>=8;bits-=8
   assert len(decoded)>=15;size=struct.unpack_from('<H',decoded,9)[0];assert len(decoded)==15+size
   assert decoded[:4]==prefix and decoded[4]==command and struct.unpack_from('<H',decoded,7)[0]==offset
   assert zlib.crc32(decoded[:-4])==struct.unpack_from('<I',decoded,len(decoded)-4)[0]
   return decoded[5],decoded[6],bytes(decoded[11:-4]),packets
  data=bytearray();identity=None;session=0x56a13f71
  while len(data)<BUNDLE_BYTES:
   status,phase,payload,_=rpc(9,len(data),token=session);assert not status and payload[:2]==b'\1\7'
   crc,count=struct.unpack_from('<IH',payload,2);assert identity is None or identity==crc;identity=crc
   data.extend(unpack_snapshot(payload[8:],count));assert phase==(0 if len(data)==BUNDLE_BYTES else 2)
  original=bytes(data);validate(original);assert snapshot_crc(original)==identity
  # Codec 2 is opt-in; its shorter response must still reconstruct the exact
  # live bundle and reject an unknown codec without taking snapshot ownership.
  compact=bytearray();wire_bytes=0
  while len(compact)<BUNDLE_BYTES:
   status,phase,payload,_=rpc(9,len(compact),b'\2',token=0x6a713f71)
   assert not status and payload[:2]==b'\2\7'
   crc,count=struct.unpack_from('<IH',payload,2);assert crc==identity
   compact.extend(unpack_snapshot(payload[8:],count,2));wire_bytes+=len(payload)+15
  assert bytes(compact)==original and wire_bytes<160
  dictionary=bytearray();dictionary_wire=0
  while len(dictionary)<BUNDLE_BYTES:
   offset=len(dictionary)
   status,phase,payload,_=rpc(9,offset,b'\3',token=0x6a713f72)
   assert not status and payload[:2]==b'\3\7'
   crc,count=struct.unpack_from('<IH',payload,2);assert crc==identity
   dictionary.extend(unpack_snapshot(payload[8:],count,3,offset));dictionary_wire+=len(payload)+15
  assert bytes(dictionary)==original and dictionary_wire<90
  assert rpc(9,body=b'\4')[0]==3
  assert m.read32(HOST+0x5c)==0
  patch=struct.pack('<IHB',identity,119,1)+bytes([(original[119]+1)%3])
  desired=bytearray(original);desired[119]=(original[119]+1)%3;struct.pack_into('<I',desired,156,zlib.crc32(desired[:156]))
  status,phase,payload,_=rpc(10,body=patch);assert (status,phase,payload)==(0,4,struct.pack('<I',snapshot_crc(desired)))
  assert m.read(m.symbols['state']+107,1)==desired[119:120] and m.read32(HOST+0x5c)==0
  assert rpc(10,body=patch)[0]==2,'Stale baseline was applied'
  restore=struct.pack('<IHB',snapshot_crc(desired),119,1)+original[119:120]
  assert rpc(10,1,restore)[:3]==(0,5,struct.pack('<I',identity))
  assert m.read32(HOST+0x5c)>0 and m.read32(HOST+0x60)==0
  short=struct.pack('<IBB',identity,119,desired[119])
  assert rpc(10,body=short)[:3]==(0,4,struct.pack('<I',snapshot_crc(desired)))
  assert rpc(10,body=short)[0]==2
  assert rpc(10,body=struct.pack('<IBB',snapshot_crc(desired),8,1))[0]==3
  assert rpc(10,body=struct.pack('<IBB',snapshot_crc(desired),119,original[119]))[:3]==(0,4,struct.pack('<I',identity))
  # No key or modifier is released by a read response; Apple Fn stays zero.
  m.write(m.symbols['key_owners']+4,b'\1');m.write(m.symbols['key_owners']+0xe1,b'\1')
  status,_,_,packets=rpc(9,token=0x42651379);assert not status
  assert packets and all(p[1]==2 and p[3]==4 and p[8]==0 for p in packets)
  m.write(m.symbols['key_owners']+4,b'\0');m.write(m.symbols['key_owners']+0xe1,b'\0')
  assert m.read(m.symbols['active_slot'],1)==b'\1' and not m.endpoint_in(1)
  unchanged=m.read(m.symbols['state'],116);writes=m.read32(HOST+0x5c)
  for symbol in fast_symbols(10,struct.pack('<I',0x53917a21),0,patch,corrupt=True):
   value=symbol<<3;inject(bytes([0x5a,value,(0x5a+value)&255]))
  step(50);assert m.read(m.symbols['state'],116)==unchanged and m.read32(HOST+0x5c)==writes
  # A dense snapshot is frozen across chunks and released by a route change.
  m.write(m.symbols['f75_custom_config']+360,bytes(i*29%256 for i in range(810)))
  status,phase,payload,_=rpc(9,body=b'\3',token=0x24157369);assert status==0 and phase==2
  assert payload[:2]==b'\3\7'
  count=struct.unpack_from('<H',payload,6)[0];assert 0<count<BUNDLE_BYTES
  m.write32(HOST+0x204,1<<2);step(100)
  assert m.read(m.symbols['transfer']+BUNDLE_BYTES+14,1)==b'\0'
  return dict(status='passed',candidate_sha256=hashlib.sha256(Path(image).read_bytes()).hexdigest(),fast_full_snapshot_crc=True,compact_snapshot_byte_exact=True,compact_response_bytes=wire_bytes,dictionary_snapshot_byte_exact=True,dictionary_response_bytes=dictionary_wire,unknown_codec_rejected=True,atomic_ram_apply_live_crc=True,stale_baseline_rejected=True,save_waits_for_reserved_flash=True,held_keys_and_modifiers_preserved=True,corrupt_frame_no_apply=True,dense_read_frozen_and_route_cancelled=True,apple_fn_never_used=True,usb_not_enumerated=True,physical_radio_tested=False)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('image',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args();r=run(a.image);a.output.write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r))
