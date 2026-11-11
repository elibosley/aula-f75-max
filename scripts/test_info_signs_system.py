#!/usr/bin/env python3
"""Verify sign-mode notices and read progress through linked USB handlers."""
import argparse,ctypes,hashlib,json,struct
from pathlib import Path
from display_types import View
from host_display import payload
from serve_emulator import Emulator

def run(image,output):
 emulator=Emulator(image);machine=emulator.machine;root=output.parent;root.mkdir(parents=True,exist_ok=True)
 try:
  emulator.advance(2500)
  def view():return View.from_buffer_copy(machine.read(machine.symbols['frame'],ctypes.sizeof(View)))
  def request(magic,data=bytes(24)):
   emulator.reports.clear();machine.endpoint_out(3,magic+b'sign'+data);emulator.advance(160)
   replies=[bytes.fromhex(r['data']) for r in emulator.reports if r['endpoint']==2]
   assert len(replies)==1 and replies[0][4:8]==b'sign';return replies[0]
  images=[]
  for character in range(4):
   machine.write(machine.symbols['state']+115,bytes([character]));emulator.advance(160)
   request(b'F75y',payload('set','Build passed',2));frame=view()
   assert frame.home and frame.pet_info and frame.pet_character==character and frame.info_progress==255
   assert bytes(frame.footer)==b'Build passed'
   filename=f'info-character-{character}.png';emulator.frame.save(root/filename);images.append(filename)
   emulator.advance(2100);assert not view().pet_info
  def transfer(op,offset=0,data=b''):
   return request(b'F75u',struct.pack('<IBH',0x12345678,op,offset)+data.ljust(17,b'\0'))
  transfer(4);assert view().pet_info and view().info_progress==0
  transfer(5,1024);frame=view();assert frame.pet_info and frame.info_progress==(1024+17)*100//3232
  assert bytes(frame.footer)==b'Sending settings'
  emulator.frame.save(root/'info-transfer.png')
  transfer(6);emulator.advance(2000);assert not view().pet_info
  request(b'F75y',payload('set','Meeting in 5 min',10))
  request(b'F75y',payload('set','Download complete',2))
  assert view().pet_info and bytes(view().footer)==b'Download complete'
  emulator.advance(2100);assert not view().pet_info
  request(b'F75y',payload('set','Message',10));emulator.action('press');assert not view().home and not view().pet_info
  emulator.action('back');assert view().home and view().pet_info
  request(b'F75y',payload('clear'));assert not view().pet_info
  result={'status':'passed','candidate_sha256':hashlib.sha256(image.read_bytes()).hexdigest(),'characters':4,'real_usb_handlers':True,'status_expiry_and_menu_priority':True,'notification_replacement_and_expiry':True,'acknowledged_read_progress':True,'screenshots':images+['info-transfer.png'],'hardware_accessed':False}
 finally:machine.close()
 output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('image',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args();run(a.image,a.output)
