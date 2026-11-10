#!/usr/bin/env python3
"""Gauge framing, failure handling and Home labels in the linked ARM image."""
import argparse,os,json,struct,hashlib
from pathlib import Path
from unicorn import UC_HOOK_MEM_READ
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('image',type=Path);parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args()
if args.image.suffix!='.bin' or args.output.suffix!='.json':
 parser.error('Use a .bin input image and a separate .json output receipt')
os.environ['F75_IMAGE']=str(args.image.resolve())
from test_keyboard_image import Candidate,SYMBOLS,IMAGE,GPIO

results={}
# Actual GPIO bit-banging: three acknowledgments and the eight data bits.
for nack in [False,True]:
 fw=Candidate();fw.word(GPIO[0],(1<<14)|(1<<15));fw.word(GPIO[0]+4,(1<<14)|(1<<15))
 samples=[1] if nack else [0,0,0]+[(0xab>>i)&1 for i in range(7,-1,-1)]
 remaining=list(samples)
 def read(cpu,access,address,size,value,data):
  if address==GPIO[0]:
   assert remaining,'unexpected gauge sample'
   bit=remaining.pop(0);fw.word(address,(fw.word(address)&~(1<<15))|(bit<<15))
 fw.cpu.hook_add(UC_HOOK_MEM_READ,read)
 assert bool(fw.call('f75_battery_read_register',4,0x20006200))!=nack
 assert not remaining
 if not nack:assert fw.byte(0x20006200)==0xab
results['gpio_read_and_nack']=True
# Coherent voltage/SOC, validation, stale data and unavailable sensor.
fw=Candidate();registers={2:0x32,3:0,4:0x30,5:0};calls=[]
def gauge(args):
 calls.append(args[0]);fw.byte(args[1],registers[args[0]]);return 1
fw.callback('f75_battery_read_register',gauge)
for t in range(1000,1004):fw.call('f75_battery_task',t)
assert calls==[2,3,4,5]
assert fw.call('f75_battery_percent',0x20006200)==1 and fw.byte(0x20006200)==50
fw.call('f75_battery_diagnostics',0x20006200)
assert struct.unpack('<6I',fw.cpu.mem_read(0x20006200,24))[:4]==(1,50,4000,1)
fw.callback('f75_battery_read_register',lambda args:0)
fw.call('f75_battery_task',40000);assert fw.call('f75_battery_percent',0x20006200)==0
for values in [(0,0,0x30,0),(0x32,0,0xff,0xff)]:
 fw=Candidate();registers=dict(zip(range(2,6),values));fw.callback('f75_battery_read_register',gauge)
 for t in range(1000,1004):fw.call('f75_battery_task',t)
 assert fw.call('f75_battery_percent',0x20006200)==0
results['coherent_percent_voltage_invalid_and_stale']=True
fw=Candidate();fw.initialize_app();fw.byte(SYMBOLS['active_slot'],1)
fw.callback('f75_radio_connected',lambda args:1)
fw.callback('f75_battery_task',lambda args:0)
fw.callback('f75_radio_task',lambda args:0)
fw.callback('f75_panel_tile',lambda args:1)
fw.byte(SYMBOLS['panel_ready'],1)
def draw(now):
 fw.now=now;fw.byte(SYMBOLS['frame_pending'],0);fw.word(SYMBOLS['last_frame'],0)
 fw.call('housekeeping_task_user')
draw(5000)
def fields():
 data=bytes(fw.cpu.mem_read(SYMBOLS['frame'],180))
 return data[8:16].split(b'\0')[0],data[136:157].split(b'\0')[0]
assert fields()==(b'--%',b''),fields()
def known(args):fw.byte(args[0],91);return 1
fw.callback('f75_battery_percent',known);draw(5010)
assert fields()==(b'91%',b''),fields()
fw.callback('f75_radio_connected',lambda args:0);draw(5020)
assert fields()[1]==b'Offline / Fn+P',fields()
fw.byte(SYMBOLS['active_slot'],4);draw(5030)
assert fields()[1]==b'Receiver offline',fields()
results['header_percent_and_contextual_pair_hint']=True
out={'status':'passed','candidate_sha256':hashlib.sha256(IMAGE.read_bytes()).hexdigest(),'checks':results,'hardware_writes':False}
args.output.write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out))
