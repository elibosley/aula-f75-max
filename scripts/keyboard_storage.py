#!/usr/bin/env python3
"""Read external asset storage through fixed ID/read operations; never program it."""
import argparse,hashlib,json,os,struct
from pathlib import Path
from keyboard_customize import Keyboard

def request(keyboard,operation,address,length):
 reply=keyboard.raw_request(b'F75z',bytes([operation,length])+struct.pack('<I',address))
 if reply[:4]!=b'F75q' or reply[8]!=0 or reply[9]!=length or struct.unpack_from('<I',reply,10)[0]!=address:
  raise RuntimeError('Storage probe rejected or did not match request; no automatic retry')
 return reply[14:14+length]

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--address',type=lambda s:int(s,0),default=0);p.add_argument('--length',type=lambda s:int(s,0),default=0);p.add_argument('--output',type=Path);a=p.parse_args()
 if not 0<=a.address<0x1000000 or not 0<=a.length<=0x1000000-a.address:p.error('Outside 24-bit flash address range')
 if a.length and not a.output:p.error('An output file is required for a read')
 os.umask(0o077)
 with Keyboard() as keyboard:
  identity=request(keyboard,0,0,3)
  if identity in (bytes(3),b'\xff'*3):raise RuntimeError('No usable JEDEC identity; no read attempted')
  data=bytearray()
  for offset in range(0,a.length,18):data.extend(request(keyboard,1,a.address+offset,min(18,a.length-offset)))
 if a.output:
  with a.output.open('xb') as stream:stream.write(data)
 print(json.dumps(dict(jedec_id=identity.hex(),address=a.address,bytes=len(data),sha256=hashlib.sha256(data).hexdigest() if data else None,flash_write_commands_sent=False)))
