#!/usr/bin/env python3
"""Power adapters and real USB/stock-framed radio wheel reports in ARM code."""
import argparse,os,json,struct,hashlib
from pathlib import Path
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('image',type=Path);parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args()
if args.image.suffix!='.bin' or args.output.suffix!='.json':
 parser.error('Use a .bin input image and a separate .json output receipt')
os.environ['F75_IMAGE']=str(args.image.resolve())
from test_keyboard_image import Candidate,SYMBOLS,IMAGE,GPIO
from serve_emulator import Emulator

fw=Candidate();fw.initialize_app();percent=5
def battery(args):fw.byte(args[0],percent);return 1
fw.callback('f75_battery_percent',battery)
fw.byte(SYMBOLS['USBD1'],0)
def budget():return struct.pack('<I',fw.call('f75_board_power_budget',SYMBOLS['state'],1000))
stage,rgb,screen,fps=budget();assert rgb==0 and screen==10 and fps==0,(stage,rgb,screen,fps)
percent=10;assert budget()[1:]==bytes([8,25,0])
fw.byte(SYMBOLS['USBD1'],4);assert budget()[1:]==bytes([28,65,24])
percent=100;fw.callback('f75_radio_task',lambda args:0);fw.callback('f75_battery_task',lambda args:0);fw.callback('f75_panel_tile',lambda args:1)
fw.byte(SYMBOLS['panel_ready'],1);fw.now=46000;fw.call('housekeeping_task_user')
assert not fw.word(GPIO[0])&(1<<16),'Idle display backlight stayed on'
fw.call('f75_activity',SYMBOLS['state'],46001)
for now in range(46001,46025):fw.now=now;fw.call('housekeeping_task_user')
assert fw.word(GPIO[0])&(1<<16),'Activity did not restore display after fresh frame'
# The radio payload is backed by a stock-code serialization oracle.
radio=Candidate();radio.byte(SYMBOLS['selected'],1);radio.byte(SYMBOLS['seen'],1);radio.word(0x40054014,0x20)
if 'f75_radio_mouse' in SYMBOLS:radio.call('f75_radio_mouse',0,255)
else:radio.call('f75_radio_scroll',255)
radio.call('f75_radio_task',1000)
wire=bytes(w['value']&255 for w in radio.writes if w['address']==0x40054000)
assert wire==bytes.fromhex('a8000000ff00a7'),wire.hex()
# Real USB HID descriptor and endpoint delivery, without host event injection.
e=Emulator(IMAGE)
try:
 e.machine.write(e.machine.symbols['state']+107,b'\1')
 for expected,turn in [(255,1),(1,-1)]:
  e.machine.endpoint_in(4);e.action('turn',turn)
  reports=e.reports[-8:];assert any(p['endpoint']==4 and p['data']==bytes([2,0,0,0,expected,0]).hex() for p in reports),reports
finally:e.machine.close()
x={'status':'passed','candidate_sha256':hashlib.sha256(IMAGE.read_bytes()).hexdigest(),'hardware_writes':False,'critical_and_low_battery_policy':True,'usb_power_uses_configured_budget':True,'idle_display_off_and_fresh_wake':True,'radio_wheel_matches_stock_format':True,'usb_wheel_both_directions':True}
args.output.write_text(json.dumps(x,indent=2)+'\n');print(json.dumps(x))
