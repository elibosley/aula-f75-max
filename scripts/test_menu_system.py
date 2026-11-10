#!/usr/bin/env python3
"""Pixel and held-button regressions against the actual linked ARM image."""
import argparse,hashlib,json,os,struct,subprocess
from pathlib import Path
from PIL import Image
from system_emulator import ROOT,HOST,NM

def run(image,out):
 os.environ['F75_IMAGE']=str(image.resolve())
 from test_keyboard_image import Candidate,SYMBOLS
 from serve_emulator import Emulator
 class Headless(Emulator):
  def close(self):self.machine.close()
 e=Headless(image)
 try:
  frame_size=None
  for line in subprocess.check_output([str(NM),'-S',str(image.with_suffix('.elf'))],text=True).splitlines():
   fields=line.split()
   if len(fields)==4 and fields[3]=='frame':frame_size=int(fields[1],16)
  assert frame_size
  renderer=Candidate()
  def check_pixels(name):
   e.advance(500)
   view=e.machine.read(e.machine.symbols['frame'],frame_size)
   renderer.cpu.mem_write(0x20005000,view)
   expected=Image.new('RGB',(128,128))
   for y in range(0,128,8):
    renderer.word(0x20007f00,1024) # fifth AAPCS argument: tile capacity
    assert renderer.call('f75_render_tile',0x20005000,y,8,0x20006000)==1
    pixels=bytes(renderer.cpu.mem_read(0x20006000,2048))
    for i,(p,) in enumerate(struct.iter_unpack('<H',pixels)):
     expected.putpixel((i%128,y+i//128),(((p>>11)&31)*255//31,((p>>5)&63)*255//63,(p&31)*255//31))
   assert e.frame.tobytes()==expected.tobytes(),f'Stale display pixels on {name}'
   e.frame.save(out/f'{name}.png')
  # Simulate existing stale panel contents. A page transition must own every
  # pixel, including strips whose new background matches the previous page.
  e.frame.paste((255,0,255),(0,0,128,128));e.updated_rows.clear()
  e.action('press');assert e.state()['page']==1
  assert e.updated_rows==set(range(128)),'Page transition did not repaint the whole display'
  check_pixels('menu')
  e.updated_rows.clear();e.action('press');assert e.state()['page']==2
  assert e.updated_rows==set(range(128))
  check_pixels('devices')
  e.machine.write32(HOST+0x100+14*4,1);e.advance(700)
  assert e.state()['page']==1,'Back waited for wheel release'
  e.advance(800);assert e.state()['page']==1,'Held Back repeated across pages'
  e.machine.write32(HOST+0x100+14*4,0);e.advance(100)
  assert e.state()['page']==1,'Release after Back clicked a menu item'
  e.action('turn',1);e.action('turn',1);e.action('press');assert e.state()['page']==4
  check_pixels('lighting')
  for _ in range(3):e.action('press');check_pixels('lighting-change')
  e.action('back');assert e.state()['page']==1
  e.frame.paste((255,0,255),(0,0,128,128));e.updated_rows.clear()
  e.action('back');assert e.state()['page']==0
  assert e.updated_rows==set(range(128)),'Return Home did not repaint every row'
  assert all(color!=(255,0,255) for _,color in e.frame.getcolors(16384))
  e.frame.save(out/'home-return.png')
  return dict(status='passed',candidate_sha256=hashlib.sha256(image.read_bytes()).hexdigest(),hardware_writes=False,
   full_page_spi_coverage=True,stale_pixels_cleared=True,decoded_spi_matches_arm_renderer=True,
   back_fires_while_held=True,hold_does_not_repeat=True,release_does_not_click=True,home_return_repaints=True,screenshots=['menu.png','devices.png','lighting.png','lighting-change.png','home-return.png'])
 finally:e.close()

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('image',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.parent.mkdir(parents=True,exist_ok=True)
 result=run(a.image,a.output.parent);a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
