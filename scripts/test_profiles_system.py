#!/usr/bin/env python3
"""Exercise three OS profiles, wheel selection, wire reports and persistent Android settings."""
import argparse,hashlib,json,struct,tempfile
from pathlib import Path
from serve_emulator import Emulator
from system_emulator import System,HOST
from test_system_emulator import enumerate_usb


def run(image,out):
 e=Emulator(image)
 try:
  m=e.machine
  def mode():return m.read(m.symbols['state'],1)[0],bool(m.read(m.symbols['state']+114,1)[0]&1)
  # Real wheel presses cycle the active USB profile, leaving other devices alone.
  others=m.read(m.symbols['state']+1,4)
  e.action('press');e.action('turn',1);e.action('press');assert e.state()['page']==3
  for os,auto in [(0,False),(1,False),(2,False),(2,True)]:
   e.action('press');assert mode()==(os,auto),mode()
  assert m.read(m.symbols['state']+1,4)==others
  # Keep Android manual and save through the same wheel path used on hardware.
  for _ in range(3):e.action('press')
  assert mode()==(2,False)
  for _ in range(4):e.action('turn',1)
  e.action('press');e.advance(100);pages=m.read(0x38000,8192)
  e.action('back');e.action('back')
  # Render all icons with all source labels and both themes through actual panel SPI.
  for theme in [0,1]:
   m.write(m.symbols['state']+113,bytes([theme]))
   for os in range(3):
    m.write(m.symbols['state'],bytes([os]));m.write(m.symbols['state']+114,b'\0');e.advance(250)
    e.frame.save(out/f'os-{os}-theme-{theme}-manual.png')
  # Actual USB interrupt-IN reports prove physical Caps policy for every OS.
  keymap=struct.unpack('<90H',m.read(m.symbols['keymaps'],180))
  for os in range(3):
   m.write(m.symbols['state'],bytes([os]));m.write(m.symbols['state']+114,b'\0')
   for usage,expected_modifier,expected_usage in [(0x39,8 if os==0 else 1,0),(0xe0,1 if os==0 else 0,0 if os==0 else 0x39)]:
    row,col=divmod(keymap.index(usage),6);e.reports=[]
    m.write32(HOST+0x100+row*4,1<<col);e.advance(25)
    packets=[bytes.fromhex(p['data']) for p in e.reports if p['endpoint']==1]
    assert packets,(os,usage,'No report')
    assert packets[-1][0]==expected_modifier and packets[-1][2]==expected_usage,(os,usage,packets[-1])
    m.write32(HOST+0x100+row*4,0);e.advance(25)
 finally:e.machine.close()
 with tempfile.TemporaryDirectory() as d:
  data=bytearray(image.read_bytes());data[0x38000:0x3a000]=pages;p=Path(d)/'saved.bin';p.write_bytes(data)
  with System(p,symbols_file=image.with_suffix('.elf')) as m:
   enumerate_usb(m);m.write32(HOST+0x30,0);m.advance(400);m.pump()
   assert m.read(m.symbols['state'],1)==b'\2' and not m.read(m.symbols['state']+114,1)[0]&1,'Android manual profile did not survive restart'
 return dict(status='passed',candidate_sha256=hashlib.sha256(image.read_bytes()).hexdigest(),hardware_writes=False,
  actual_wheel_auto_manual_cycle=True,per_device_isolation=True,mac_caps_command=True,mac_left_ctrl_control=True,windows_android_caps_ctrl=True,manual_android_save_restart=True,spi_icon_screenshots=True)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('image',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 result=run(a.image,a.output.parent);a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
