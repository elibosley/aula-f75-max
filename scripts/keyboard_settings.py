#!/usr/bin/env python3
"""Read the two fixed settings records, or explicitly request onboard Save."""
import argparse,json,secrets,struct,sys,hashlib,datetime
from pathlib import Path
import hid
from keyboard_transport_lock import TransportLock
ROOT=Path(__file__).resolve().parents[1]

def exchange(request,payload=b''):
 devices=[d for d in hid.enumerate(0xfeed,0xf750) if d['usage_page']==0xff60]
 if len(devices)!=1:raise RuntimeError('Exactly one diagnostics interface required')
 nonce=secrets.token_bytes(4);packet=request+nonce+payload+bytes(24-len(payload))
 with TransportLock(), hid.Device(path=devices[0]['path']) as d:
  d.write(b'\0'+packet);reply=bytes(d.read(32,1500))
 if len(reply)!=32 or reply[4:8]!=nonce:raise RuntimeError('Settings reply nonce mismatch')
 return reply

def snapshot():
 r=exchange(b'F75n');assert r[:4]==b'F75m'
 return dict(zip(['loaded','generation','active_record','successful_saves','failed_saves','record_bytes'],struct.unpack_from('<6I',r,8)))

def capture(source_sha):
 before=snapshot()
 health=exchange(b'F75?');assert health[:4]==b'F75!'
 route_supported=bool(health[24]&32)
 records=[]
 for slot in range(2):
  data=bytearray()
  for chunk in range(8):
   r=exchange(b'F75r',bytes([slot,chunk]));assert r[:4]==b'F75s' and r[8:10]==bytes([slot,chunk]);data.extend(r[10:30])
  records.append(data.hex())
 image=ROOT/'analysis/candidates'/source_sha/'f75max-wired-test.bin'
 data=bytearray(image.read_bytes());assert hashlib.sha256(data).hexdigest()==source_sha
 regions=[]
 for address,record in zip([0x3f000,0x3f400],records):data[address:address+160]=bytes.fromhex(record)
 if before['record_bytes']==4096:
  for slot,address in enumerate([0x38000,0x39000]):
   value=bytearray()
   for offset in range(0,4096,20):
    r=exchange(b'F75j',bytes([slot])+struct.pack('<H',offset));assert r[:4]==b'F75k' and r[8:11]==bytes([slot])+struct.pack('<H',offset);value.extend(r[12:32])
   value=bytes(value[:4096]);data[address:address+4096]=value;regions.append({'address':address,'hex':value.hex()})
 route_regions=[]
 if route_supported:
  stamp=exchange(b'F75j',bytes([2,255,255]));assert stamp[:4]==b'F75k'
  value=bytearray()
  for offset in range(0,2048,20):
   r=exchange(b'F75j',bytes([2])+struct.pack('<H',offset));assert r[:4]==b'F75k' and r[8:11]==bytes([2])+struct.pack('<H',offset);value.extend(r[12:32])
  if exchange(b'F75j',bytes([2,255,255]))[8:]!=stamp[8:]:raise RuntimeError('Bluetooth route changed during backup')
  value=bytes(value[:2048]);data[0x3e800:0x3f000]=value;route_regions=[dict(address=0x3e800,hex=value.hex())]
 status=exchange(b'F75o');assert status[:4]==b'F75p'
 last_connected_bt=status[10] if 1<=status[10]<=3 and status[19]&1 else None
 after=snapshot()
 if before!=after:raise RuntimeError('Settings changed during backup; capture again before flashing')
 checksum=sum(struct.unpack('<131072H',data))&65535
 return {'observed_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'source_image_sha256':source_sha,'source_checksum':f'{checksum:04x}','records_hex':records,'custom_regions':regions,'route_regions':route_regions,'last_connected_bt':last_connected_bt,'stats':after}

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--save',action='store_true');p.add_argument('--capture',type=Path);p.add_argument('--source-sha');p.add_argument('--debug',action='store_true');p.add_argument('--os',action='store_true');a=p.parse_args()
 if a.save:
  r=exchange(b'F75w',b'SAVECFG!');assert r[:4]==b'F75v';print(json.dumps({'save_requested':True,'completion':'Read counters after task commits'}))
 elif a.capture:
  if not a.source_sha:p.error('--capture requires --source-sha')
  x=capture(a.source_sha);a.capture.write_text(json.dumps(x,indent=2)+'\n');print(json.dumps({'backup':str(a.capture),'checksum':x['source_checksum'],'stats':x['stats']}))
 elif a.debug:
  r=exchange(b'F75f');assert r[:4]==b'F75g';print(json.dumps(dict(zip(['flash_status','flash_control','flash_address','generation','successful_saves','failed_saves'],struct.unpack_from('<6I',r,8))),indent=2))
 elif a.os:
  r=exchange(b'F75o');assert r[:4]==b'F75p';print(json.dumps({'usb_detected':r[8],'auto_mask':r[9],'active_slot':r[10],'slot_os':list(r[11:16]),'caps_swap':bool(r[16])},indent=2))
 else:print(json.dumps(snapshot(),indent=2))
