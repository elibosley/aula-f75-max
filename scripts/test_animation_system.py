"""Linked ARM visitor lifecycle, quiet mode and unchanged-frame render work."""
import argparse,ctypes,hashlib,json
from pathlib import Path
from display_types import View
from serve_emulator import Emulator

def run(image,out):
 e=Emulator(image)
 try:
  m=e.machine;pet=m.symbols['pet'];state=m.symbols['state']
  def view():return View.from_buffer_copy(m.read(m.symbols['frame'],ctypes.sizeof(View)))
  def now():return m.read32(pet)
  m.write(state+103,b'\2');e.advance(1000)
  m.write(pet+92,b'\0');m.write32(pet+84,now()+200)
  e.advance(500);v=view();assert v.visitor and v.visitor_frame<8 and 79<=v.visitor_x<=128
  e.frame.save(out.parent/'visitor-walk.png')
  e.advance(2000);v=view();assert v.visitor and 8<=v.visitor_frame<12 and v.visitor_x==79
  e.frame.save(out.parent/'visitor-sit.png')
  e.advance(2000);v=view();assert v.visitor and 12<=v.visitor_frame<16
  e.frame.save(out.parent/'visitor-wave.png')
  m.write(state+109,b'\1');e.advance(1100);assert not view().visitor
  e.frame.save(out.parent/'visitor-quiet.png')
  m.write(state+109,b'\0');e.advance(4500);assert not view().visitor
  m.write32(pet+68,now()+100000);m.write32(pet+84,now()+100000);m.write(pet+80,b'\0');e.advance(500)
  assert view().pet_frame==5
  tiles=m.read32(m.symbols['perf_tiles']);frames=m.read32(m.symbols['complete_frames'])
  e.advance(1000)
  extra=m.read32(m.symbols['perf_tiles'])-tiles
  assert extra==0,('Unchanged sleeping pose was redrawn',extra)
  assert m.read32(m.symbols['complete_frames'])>frames,'Frame scheduler stopped'
  e.action('tap','a');assert view().pet_mode in (1,2,3) and view().pet_frame in (2,3)
  e.frame.save(out.parent/'visitor-after-typing.png')
  return dict(status='passed',candidate_sha256=hashlib.sha256(image.read_bytes()).hexdigest(),real_arm_image=True,
   visitor_walk_sit_wave_reach_panel=True,reduced_motion_hides_visitor=True,visitor_exits_and_cools_down=True,
   unchanged_pose_rendered_tiles_per_second=extra,typing_interrupts_sleep=True,hardware_writes=False,physical_hardware_tested=False)
 finally:e.machine.close()
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('image',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args();r=run(a.image,a.output);a.output.write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r))
