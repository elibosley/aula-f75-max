"""Linked ARM menu rendering: sparse rows, exact panel pixels, and input bursts."""
import argparse,ctypes,hashlib,json,os,struct
from pathlib import Path
from PIL import Image
from display_types import View
from serve_emulator import Emulator
from system_emulator import HOST


def run(image,out,baseline=False):
 os.environ['F75_IMAGE']=str(image.resolve())
 from test_keyboard_image import Candidate,SCRATCH,TILE
 e=Emulator(image);renderer=Candidate();m=e.machine
 try:
  def view():return m.read(m.symbols['frame'],ctypes.sizeof(View))
  def golden(name):
   # Compare a complete frozen frame, rather than a half-transferred panel.
   for _ in range(500):
    if not m.read(m.symbols['frame_pending'],1)[0]:break
    e.advance(1)
   else:raise AssertionError('Display did not finish a frame')
   data=view();renderer.cpu.mem_write(SCRATCH,data);expected=bytearray()
   for y in range(0,128,8):
    renderer.word(0x20007f00,1024);assert renderer.call('f75_render_tile',SCRATCH,y,8,TILE)==1
    for (p,) in struct.iter_unpack('<H',renderer.cpu.mem_read(TILE,2048)):
     expected.extend((((p>>11)&31)*255//31,((p>>5)&63)*255//63,(p&31)*255//31))
   assert e.frame.tobytes()==expected,'Panel differs from complete ARM frame: '+name
   e.frame.save(out.parent/(name+'.png'))
  def counters():return {name:m.read32(m.symbols[name]) for name in ('complete_frames','perf_tiles','perf_render_ticks','perf_spi_ticks') }|{'bytes':m.read32(m.symbols['bus'])}
  m.endpoint_out(3,b'F75AtestDRAWTEST'+bytes(16));e.advance(300);first=counters();e.advance(1500);last=counters()
  delta={key:last[key]-first[key] for key in first};frames=delta['complete_frames'];assert frames>10
  metrics=dict(frames=frames,rendered_tiles_per_frame=delta['perf_tiles']/frames,spi_bytes_per_frame=delta['bytes']/frames,**delta)
  if not baseline:
   assert metrics['rendered_tiles_per_frame']<10,metrics
   assert metrics['spi_bytes_per_frame']<5000,metrics
  # Exit the temporary diagnostic and check both cache kinds own every pixel.
  m.write(m.symbols['benchmark_active'],b'\0');e.advance(500);golden('home-after-scroll')
  e.action('press');assert e.state()['page']==1;e.advance(400);golden('menu-start')
  e.action('turn',1);assert e.state()['cursor']==1;e.advance(400);golden('menu-down')
  def detent(direction):
   seq=[3,2,0,1,3] if direction>0 else [3,1,0,2,3]
   for value in seq:
    m.write32(HOST+0x200,(1<<10)|((value&1)<<2)|((value&2)<<2));e.advance(5)
  expected_cursor=1
  for direction in [1,1,-1,-1,1,-1]:
   detent(direction);expected_cursor=(expected_cursor+direction)%6
   assert e.state()['cursor']==expected_cursor,'A rapid detent was delayed or lost'
  e.advance(500);assert e.state()['cursor']==1;golden('menu-reversal')
  # Static menu frames should cost no rendering or SPI work after settling.
  e.advance(1500);idle=counters();e.advance(500);after=counters()
  idle_tiles=after['perf_tiles']-idle['perf_tiles'];idle_bytes=after['bytes']-idle['bytes']
  if not baseline:assert idle_tiles==idle_bytes==0,(idle_tiles,idle_bytes)
  for light in (True,False):
   m.write(m.symbols['state']+113,bytes([light]));e.advance(500);golden('menu-light' if light else 'menu-dark')
  m.write(m.symbols['state']+109,b'\1');e.action('turn',1);e.advance(500);golden('menu-reduced-motion')
  e.action('press');e.advance(500);golden('submenu')
  e.action('back');e.action('back');e.advance(500);golden('home-return')
  assert m.read32(HOST+8)==0
  return dict(status='passed',candidate_sha256=hashlib.sha256(image.read_bytes()).hexdigest(),baseline_measurement=baseline,modeled_scroll=metrics,unchanged_menu_rendered_tiles=idle_tiles,unchanged_menu_spi_bytes=idle_bytes,decoded_panel_matches_full_arm_frames=True,rapid_reversals_keep_first_detent_behavior=True,themes_and_reduced_motion=True,home_menu_submenu_cache_transitions=True,hardware_writes=False,physical_hardware_tested=False)
 finally:m.close()

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('image',type=Path);p.add_argument('--output',type=Path,required=True);p.add_argument('--baseline',action='store_true');a=p.parse_args();a.output.parent.mkdir(parents=True,exist_ok=True)
 result=run(a.image,a.output,a.baseline);a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
