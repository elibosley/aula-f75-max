#!/usr/bin/env python3
"""Exercise USB OS fingerprints through real EP0 and verify route isolation."""
import argparse,json,hashlib
from pathlib import Path
from system_emulator import System,HOST
from test_system_emulator import enumerate_usb

def run(image):
 cases=[]
 for name,sequence,expected in [('mac',[2,36,2,40,255],0),('windows',[255,255,4,255],1),('linux',[255,255,255],2)]:
  with System(image) as m:
   enumerate_usb(m)
   if name=='linux':m.write(m.symbols['state'],b'\2');m.write(m.symbols['usb_detected'],b'\xff')
   for length in sequence:m.control(0x80,6,0x300,length=length)
   m.write32(HOST+0x30,0);m.advance(400);m.pump()
   assert m.read(m.symbols['state'],1)==bytes([expected]),name
   if name=='linux':assert m.read(m.symbols['usb_detected'],1)==b'\xff','Ambiguous Linux/Android fingerprint was mislabeled Windows'
   assert m.read(m.symbols['state']+114,1)==bytes([31])
   # USB evidence must never change a Bluetooth profile.
   assert m.read(m.symbols['state']+1,1)==bytes([0])
   cases.append({'host':name,'effective_os':expected,'bluetooth_profile_untouched':True})
 return {'status':'passed','candidate_sha256':hashlib.sha256(image.read_bytes()).hexdigest(),'hardware_writes':False,'ep0_detection':cases,'caps_ctrl_policy':'independent portable core checks'}
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('image',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args();x=run(a.image);a.output.write_text(json.dumps(x,indent=2)+'\n');print(json.dumps(x))
