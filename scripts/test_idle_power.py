#!/usr/bin/env python3
"""Exercise idle PWM shutdown, matrix wake and short pulses in the linked ARM image."""
import argparse,hashlib,json,struct
from pathlib import Path
from system_emulator import System,HOST
from test_system_emulator import enumerate_usb

def run(image):
 with System(image) as m:
  enumerate_usb(m);reports=[]
  def step(ms=5):
   m.write32(HOST+0x30,0);m.advance(ms);m.pump()
   for ep in (1,4):
    for _ in range(20):
     packet=m.endpoint_in(ep)
     if packet is None:break
     if ep==1:reports.append(packet)
  def query(magic):
   m.endpoint_out(3,magic+b'pow!'+bytes(24));step();reply=m.endpoint_in(2);assert reply and reply[4:8]==b'pow!';return reply
  def power():
   r=query(b'F75d');assert r[:4]==b'F75e';v=list(struct.unpack_from('<6I',r,8));v[5]&=65535;return tuple(v)
  def age():
   r=query(b'F75?');now=struct.unpack_from('<I',r,8)[0]
   m.write(m.symbols['state']+116,struct.pack('<I',(now-46000)&0xffffffff));step(40)
  def irq():return struct.unpack_from('<I',query(b'F75R'),12)[0]
  step(300);assert power()[4]==255
  age();values=power();assert values==(2,0,0,0,511,16),values
  # Execute the real scheduler's idle function, including its WFI, and
  # return through actual interrupt-driven wakeup. No function stub here.
  m.until('__idle_thread');assert m.read(m.symbols['__idle_thread'],2)==bytes.fromhex('30bf')
  m.advance(5);m.pump()
  yielded=struct.unpack_from('<I',query(b'F75d'),28)[0]>>16;assert yielded>0
  for bank in (0x40000000,0x40002000,0x40004000):assert m.read32(bank)==0,'Idle PWM timer still running'
  assert m.read32(0x400020a4)==0,'Idle PWM mux still attached'
  count=irq();frames=m.read(m.symbols['frame_count'],4);scans=m.read(m.symbols['f75_matrix_scans'],4);step(100)
  assert irq()>count and m.read(m.symbols['f75_matrix_scans'],4)!=scans,'Idle stopped key scanning'
  assert m.read(m.symbols['frame_count'],4)==frames,'Dark RGB still regenerates frames'
  for _ in range(5):query(b'F75o')
  assert power()[0]==2,'Metadata traffic woke the screen'
  keymap=struct.unpack('<90H',m.read(m.symbols['keymaps'],180))
  def key(index,down):
   row,col=divmod(index,6);m.write32(HOST+0x100+row*4,(1<<col) if down else 0)
  # The first press starts in the slower scan phase. It must not be lost.
  for usage in (0x29,4,0x4c): # first, early and last matrix drive rows
   for phase in range(8):
    age();step(phase+1);reports.clear();key(keymap.index(usage),True);step(15)
    assert bytes([0,0,usage,0,0,0,0,0]) in reports,('Idle missed 15ms key pulse',usage,phase,reports)
    assert power()[4]==255,'Raw key activity did not restore the active row period'
    key(keymap.index(usage),False);step(15);assert reports[-1]==bytes(8)
  # Fn and wheel are activity even without a host typing usage.
  age();key(71,True);step(30);assert power()[0]==0 and power()[4]==255
  key(71,False);step(30)
  age();key(84,True);step(50);assert power()[0]==0 and power()[5]&1,'Held wheel did not wake display'
  assert m.read(m.symbols['navigation'],1)==b'\0','Wheel click fired before release'
  key(84,False);step(40);assert m.read(m.symbols['navigation'],1)==b'\1','Wake swallowed the menu click'
  # Adaptive row changes cannot undo an explicit diagnostic suspension.
  m.endpoint_out(3,b'F75TdiagF75DIAG!RGB0'+bytes(12));step();assert m.endpoint_in(2)[:4]==b'F75U'
  age();assert power()[4]==511;assert m.read32(0x40006000)==0
  key(keymap.index(4),True);step(25);assert power()[4]==255 and m.read32(0x40006000)==0
  key(keymap.index(4),False);step(20);assert m.read32(HOST+8)==0
 return {'status':'passed','candidate_sha256':hashlib.sha256(Path(image).read_bytes()).hexdigest(),'hardware_writes':False,'idle_row_period_511_active_255':True,'idle_pwm_banks_stopped_mux_detached':True,'dark_color_frames_stop':True,'idle_thread_WFI_reached_and_interrupt_wake_executes':True,'metadata_does_not_wake':True,'real_usb_15ms_pulses':24,'idle_pulse_rows':[0,1,14],'idle_phases_per_key':8,'fn_and_held_wheel_wake':True,'click_after_wake_preserved':True,'diagnostic_suspend_preserved':True,'deep_sleep_or_battery_endurance':'not_claimed'}
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('image',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args();r=run(a.image);a.output.write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r))
