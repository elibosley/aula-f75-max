#!/usr/bin/env python3
"""Real ARM USB/UART/GPIO-to-display and RGB tests; no physical keyboard access."""
import argparse,ctypes,hashlib,json,os,struct
from pathlib import Path
from display_types import View
from system_emulator import System,HOST
from test_system_emulator import enumerate_usb

def run(image):
 with System(image) as m:
  m.write32(HOST+0x204,(1<<2)|(1<<17))
  enumerate_usb(m)
  def step(ms=20):
   for n in range(0,ms,2):
    m.write32(HOST+0x30,0);m.advance(min(2,ms-n));m.pump()
    if m.read(m.symbols['waiting'],1)==b'\1':
     for value in b'\x61\x0d\x0a':m.write32(HOST+0x44,value)
     m.advance(1);m.pump()
  def uart(a,b):
   for value in [a,b,(a+b)&255]:m.write32(HOST+0x44,value)
   step(80)
  def view():return View.from_buffer_copy(m.read(m.symbols['frame'],ctypes.sizeof(View)))
  def board_caps(on):
   assert m.read32(0x40046004)&2, "Dedicated Caps pin is not an output"
   assert bool(m.read32(0x40046000)&2)==on, "Dedicated Caps indicator disagrees with active host"
  def caps_pwm():
   active=m.read(m.symbols['active_buffer'],1)[0];base=m.symbols['duties']+active*270
   return tuple(m.read(base+ch*90+45,1)[0] for ch in range(3))
  def key(row,col,down):m.write32(HOST+0x100+row*4,(1<<col) if down else 0);step(60)
  # Desk, 100%, red Still base makes both indicator colors unambiguous.
  state=m.symbols['state'];m.write(state+103,b'\x02\x64');m.write(state+106,b'\0');m.write(state+110,b'\xff\0\0')
  step(200);assert (view().link_state,view().power_state)==(3,2),(view().link_state,view().power_state)
  assert caps_pwm()==(127,0,0),caps_pwm();board_caps(False)
  m.control_out(0x21,9,b'\x02',value=0x200,index=0);step(100)
  mint=tuple(c*127//255 for c in (168,234,212));lilac=tuple(c*127//255 for c in (200,170,246))
  assert caps_pwm()==mint,caps_pwm();board_caps(True)
  key(11,5,True);assert caps_pwm()==lilac;board_caps(True);key(11,5,False);assert caps_pwm()==mint;board_caps(True)
  # The board light remains useful with all key lighting disabled.
  m.write(state+104,b'\0');step(100);assert caps_pwm()==(0,0,0);board_caps(True)
  m.write(state+104,b'\x64');step(100)
  m.control_out(0x21,9,b'\0',value=0x200,index=0);step(80);assert caps_pwm()==(127,0,0);board_caps(False)
  m.write32(HOST+0x204,1<<2);step(100);assert view().power_state==3 and bytes(view().status_right)==b'--%'
  m.write32(HOST+0x204,(1<<2)|(1<<17));step(20);assert view().power_state==3
  step(80);assert view().power_state==2
  # Physical BT mode then Fn+2; explicit modeled ACKs are not a live radio.
  m.write32(HOST+0x204,1<<17);step(160)
  key(11,5,True);key(2,1,True);key(2,1,False);key(11,5,False);step(100)
  assert m.read(m.symbols['active_slot'],1)==b'\2'
  uart(0x5b,0x32);assert bytes(view().status_left)==b'BT2' and view().link_state==3
  uart(0x5a,2);assert caps_pwm()==mint;board_caps(True)
  uart(0x5a,0xe2);assert caps_pwm()==mint,'Status symbols changed Caps LED state';board_caps(True)
  uart(0x5a,0);assert caps_pwm()==(127,0,0);board_caps(False)
  m.control_out(0x21,9,b'\x02',value=0x200,index=0);step(80);assert caps_pwm()==(127,0,0),'Inactive USB host changed BT indicator';board_caps(False)
  uart(0x5a,2);uart(0x5b,0x33);assert view().link_state==1 and caps_pwm()==(127,0,0);board_caps(False)
  m.write32(HOST+0x204,(1<<2)|(1<<17));step(160);assert bytes(view().status_left)==b'USB' and caps_pwm()==mint;board_caps(True)
  return dict(status='passed',candidate_sha256=hashlib.sha256(image.read_bytes()).hexdigest(),real_arm_image=True,dedicated_caps_gpio='B1 active high',dedicated_caps_independent_of_rgb=True,usb_caps_reports=True,bluetooth_led_packets=True,fn_priority_and_release=True,inactive_host_isolation=True,disconnect_clears_caps=True,header_tracks_link_and_gpio_charge=True,unknown_percent_preserved=True,physical_hardware_tested=False)

def charge_debounce(image):
 os.environ['F75_IMAGE']=str(image.resolve())
 from test_keyboard_image import Candidate,GPIO,SCRATCH
 f=Candidate();f.callback('f75_battery_read_register',lambda args:0)
 def charge():return bool(f.call('f75_battery_charging',SCRATCH)),bool(f.byte(SCRATCH))
 f.word(GPIO[1],1<<17);f.call('f75_battery_task',1000);assert not charge()[0]
 f.call('f75_battery_task',1049);assert not charge()[0]
 f.call('f75_battery_task',1050);assert charge()==(True,False)
 f.word(GPIO[1],0);f.call('f75_battery_task',1060);f.call('f75_battery_task',1109);assert charge()==(True,False)
 f.call('f75_battery_task',1110);assert charge()==(True,True)
 f.word(GPIO[1],1<<17);f.call('f75_battery_task',0xfffffff0);f.call('f75_battery_task',0x21);assert charge()==(True,True)
 f.call('f75_battery_task',0x22);assert charge()==(True,False)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('image',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args();result=run(a.image);charge_debounce(a.image);result['charge_debounce_and_wrap']=True;a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
