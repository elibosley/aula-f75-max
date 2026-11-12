"""Count linked Cortex-M0 render instructions; no physical keyboard or OS events."""
import argparse,ctypes,hashlib,json,os
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('image',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
os.environ['F75_IMAGE']=str(a.image.resolve())
from test_keyboard_image import Candidate,SCRATCH,TILE
from display_types import View
from unicorn import UC_HOOK_CODE
machine=Candidate();instructions=[0]
def count(*_):instructions[0]+=1
machine.cpu.hook_add(UC_HOOK_CODE,count)
records=[]
for character in range(4):
 view=View();view.home=True;view.face=3;view.pet_character=character;view.pet_frame=2;view.pet_mode=1;view.clock=b'12:34';view.status_left=b'BT2';view.status_right=b'78%';view.os=b'MAC'
 machine.cpu.mem_write(SCRATCH,bytes(view));pixels=bytearray();samples=[]
 for y in range(0,128,8):
  machine.word(0x20007f00,1024);instructions[0]=0
  assert machine.call('f75_render_tile',SCRATCH,y,8,TILE)==1
  samples.append(instructions[0]);pixels.extend(machine.cpu.mem_read(TILE,2048))
 records.append(dict(character=character,total_instructions=sum(samples),max_tile_instructions=max(samples),tiles=samples,pixel_sha256=hashlib.sha256(pixels).hexdigest()))
result=dict(status='passed',image_sha256=hashlib.sha256(a.image.read_bytes()).hexdigest(),metric='Cortex-M0 instruction count; not wall-clock FPS',characters=records,physical_hardware_tested=False)
a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
