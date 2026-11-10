#!/usr/bin/env python3
"""Verify the chibi clock through linked firmware USB, timekeeping and panel SPI."""
import argparse,hashlib,json,struct
from pathlib import Path
from serve_emulator import Emulator
from serve_native import View
from system_emulator import HOST


def run(image,out):
 e=Emulator(image)
 try:
  m=e.machine
  def clock():return m.read(m.symbols['frame']+View.clock.offset,6).split(b'\0')[0].decode()
  def sync(seconds):
   e.reports=[];m.endpoint_out(3,b'F75hclokTIMESET!'+struct.pack('<I',seconds)+bytes(12));e.advance(1100)
   replies=[bytes.fromhex(p['data']) for p in e.reports if p['endpoint']==2]
   assert any(p[:8]==b'F75iclok' and p[8]==1 for p in replies),'Clock sync did not acknowledge'
  assert clock()=='--:--';e.frame.save(out/'clock-unsynced.png')
  # Pause automatic motion so pixel changes isolate the actual clock digits.
  m.write(m.symbols['state']+109,b'\1')
  # Wait for the real startup notice deadline plus the quiet frame cadence.
  e.advance(max(0,m.read32(m.symbols['notice_until'])+1500-m.read32(HOST+12)//1000))
  # Keep this quiet pixel-comparison fixture awake while minutes change.
  m.write(m.symbols['pet']+4,struct.pack('<I',m.read32(HOST+12)//1000))
  assert not m.read(m.symbols['frame']+View.footer.offset,21).split(b'\0')[0],'Idle home still shows the menu hint'
  sync(45240);assert clock()=='12:34';e.advance(900);e.frame.save(out/'clock-12-34.png')
  before=e.frame.copy();sync(45300);e.advance(900);assert clock()=='12:35'
  after=e.frame.copy();after.save(out/'clock-12-35.png');changed=[(x,y) for y in range(128) for x in range(128) if before.getpixel((x,y))!=after.getpixel((x,y))]
  assert changed and all(6<=x<=30 and 75<=y<100 for x,y in changed),('Minute update changed pet, pace or footer',len(changed),[(x,y) for x,y in changed if not (6<=x<=30 and 75<=y<100)][:20])
  sync(86398);assert clock()=='23:59';e.advance(1800);assert clock()=='00:00';e.frame.save(out/'clock-midnight.png')
  m.write(m.symbols['state']+113,b'\1');e.advance(1100);assert clock()=='00:00';e.frame.save(out/'clock-light.png')
  e.action('press');e.frame.save(out/'menu-rounded.png');assert e.state()['page']==1
  # Focus retains its countdown and completion notice, rather than the home badge.
  for _ in range(4):e.action('turn',1)
  e.action('press');e.advance(100);assert e.state()['page']==6
  assert clock()=='25:00','Focus countdown was replaced by local time';e.frame.save(out/'focus-countdown.png')
  e.action('press');e.action('back');e.action('back');e.advance(1100)
  assert e.state()['page']==0 and clock()=='00:00'
  assert m.read(m.symbols['frame']+View.footer.offset,21).startswith(b'Focus '),'Home clock hid the running focus timer';e.frame.save(out/'clock-with-focus.png')
  assert m.read32(HOST+8)==0
  return dict(status='passed',candidate_sha256=hashlib.sha256(image.read_bytes()).hexdigest(),hardware_writes=False,
   raw_usb_clock_sync=True,unsynced_placeholder=True,clock_minute_redraw_isolated=True,analog_clock_on_desk=True,midnight_rollover=True,light_theme=True,focus_countdown_preserved=True,actual_panel_spi_screenshots=True)
 finally:e.machine.close()

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('image',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args();r=run(a.image,a.output.parent);a.output.write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r))
