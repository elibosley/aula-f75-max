#!/usr/bin/env python3
"""Exercise the actual ARM transport adapter with explicit modeled UART replies.

No Bluetooth controller or wireless link is emulated. This verifies byte framing,
input routing, selector priority, and bounded failures, not physical pairing.
"""
import argparse,hashlib,json,struct
from pathlib import Path
from system_emulator import System,HOST
from test_system_emulator import enumerate_usb

def run(image):
 with System(image) as m:
  m.until('housekeeping_task_user')
  auto_ack=False
  def step(ms=5):
   for elapsed in range(0,ms,2):
    m.write32(HOST+0x30,0);m.advance(min(2,ms-elapsed));m.pump()
    if auto_ack and waiting():
     for byte in b'\x61\x0d\x0a':m.write32(HOST+0x44,byte)
     m.advance(1);m.pump()
  def inject(data):
   for byte in data:m.write32(HOST+0x44,byte)
   step(2)
  def trace():return m.read(0x61000000,m.read32(HOST+0x40))
  def frames():return struct.unpack('<I',m.read(m.symbols['complete_frames'],4))[0]
  def slot():return m.read(m.symbols['active_slot'],1)[0]
  def waiting():return bool(m.read(m.symbols['waiting'],1)[0])
  def settle():
   for _ in range(12):
    step(2)
    if waiting():inject(b'\x61\x0d\x0a')
  keymap=struct.unpack('<90H',m.read(m.symbols['keymaps'],180))
  def position(usage):
   index=keymap.index(usage);return divmod(index,6)
  def key_at(row,col,down):
   m.write32(HOST+0x100+row*4,(1<<col) if down else 0);step(20)
  def key(usage,down):key_at(*position(usage),down)
  def chord(usage):
   key_at(11,5,True);key(usage,True);key(usage,False);key_at(11,5,False)
  def selector(mode):
   m.write32(HOST+0x200,(1<<10 if mode!=2 else 0)|(1<<2)|(1<<3))
   m.write32(HOST+0x204,1<<2 if mode!=1 else 0);step(25);step(25)
  step(60)
  before=frames();step(100);assert frames()>before,'USB absence stopped the main task'
  assert m.read32(0x40042008)&0xf00==0xf00
  assert m.read32(0x40046008)&0xf000==0,'UART pull-ups differ from stock'
  assert b'\xa6\x11\xb7' in trace()
  # Without a radio reply, a hotkey must preserve the selected USB route.
  chord(0x1e);assert slot()==0
  auto_ack=True
  selector(1);assert slot()==1
  settle();inject(bytes([0x5b,0x32,0x8d]));settle()
  assert b'\xa6\x31\xd7' in trace()
  assert m.read(m.symbols['connected'],1)==b'\1', {'trace':trace().hex(),'state':{n:m.read(m.symbols[n],4).hex() for n in ['route_acked','seen','waiting','last_event','errors','rx_errors','rx_head','rx_tail','head','tail','last_command']}}
  offset=len(trace());key(4,True);settle();key(4,False);settle()
  data=trace()[offset:]
  assert bytes([0xa1,0,0,4,0,0,0,0,0,0xa5]) in data,data.hex()
  assert bytes([0xa1,0,0,0,0,0,0,0,0,0xa1]) in data
  for physical,expected in [(0x39,bytes([8,0,0,0,0,0,0,0])),(0xe0,bytes([0,0,0x39,0,0,0,0,0]))]:
   offset=len(trace());key(physical,True);settle();key(physical,False);settle()
   packet=bytes([0xa1])+expected+bytes([(0xa1+sum(expected))&255])
   assert packet in trace()[offset:],('Bluetooth Caps/Ctrl mapping',physical,trace()[offset:].hex())
   assert bytes([0xa1]+[0]*8+[0xa1]) in trace()[offset:]
  # A missing UART report ACK is not an RF disconnection. The physical
  # board can still type while this flag is falsely cleared by a timeout.
  auto_ack=False;before=m.read32(m.symbols['errors']);offset=len(trace())
  key(4,True);step(100)
  assert bytes.fromhex('a10000040000000000a5') in trace()[offset:],'Fixture did not transmit a keyboard report'
  assert m.read32(m.symbols['errors'])>before,'Fixture did not exhaust report ACK retries'
  assert m.read(m.symbols['connected'],1)==b'\1','UART report timeout falsely claimed an RF disconnect'
  auto_ack=True;key(4,False);settle()
  # Battery-route idle must keep UART RX/ACK processing and first-key delivery
  # alive even though USB has not been configured in this test yet.
  age=struct.unpack('<I',m.read(m.symbols['state']+116,4))[0]
  m.write(m.symbols['state']+116,struct.pack('<I',(age-46000)&0xffffffff));step(50)
  assert m.read32(0x40006020)==511,'Wireless idle did not slow the row clock'
  offset=len(trace());key(4,True);settle();key(4,False);settle()
  assert bytes.fromhex('a10000040000000000a5') in trace()[offset:],'Idle lost the first radio key report'
  assert m.read32(0x40006020)==255 and m.read(m.symbols['connected'],1)==b'\1'
  offset=len(trace());chord(0x1f);assert slot()==2;settle()
  empty_mouse=bytes.fromhex('a80000000000a8');route=bytes.fromhex('a632d8')
  assert empty_mouse in trace()[offset:] and trace()[offset:].index(empty_mouse)<trace()[offset:].index(route),'Mouse release did not precede route change'
  data=trace()[offset:];assert b'\xa6\x32\xd8' in data and b'\xa6\x51\xf7' not in data
  command=data.index(b'\xa6\x32\xd8');assert bytes([0xa1]+[0]*8+[0xa1]) in data[:command]
  chord(0x22);assert slot()==2,'USB request without an enumerated host replaced Bluetooth'
  enumerate_usb(m);assert slot()==2,'USB enumeration replaced selected wireless route'
  m.endpoint_out(3,b'F75Ouart'+bytes(24));step(20)
  reply=m.endpoint_in(2);assert reply and len(reply)==32 and reply[:8]==b'F75Zuart'
  assert struct.unpack_from('<I',reply,8)[0]&1
  chord(0x22);assert slot()==0;settle()
  selector(2);assert slot()==4;settle()
  selector(1);assert slot()==2;settle()
  # Fn+wheel click returns to the previous BT slot and consumes the whole
  # button gesture, including a hold, without opening a menu or pairing.
  offset=len(trace());key_at(11,5,True);key_at(14,0,True);step(750);key_at(14,0,False);key_at(11,5,False);settle()
  assert slot()==1 and m.read(m.symbols['navigation'],1)==b'\0'
  key_at(11,5,True);key_at(14,0,True);key_at(14,0,False);key_at(11,5,False);settle();assert slot()==2
  assert b'\xa6\x51\xf7' not in trace()[offset:],'Previous-device shortcut started pairing'
  selector(0);assert slot()==0;settle();selector(1);assert slot()==2;settle()
  # Pairing requires an explicit request followed by a separate held-wheel action.
  offset=len(trace());chord(0x13);key_at(14,0,True);step(200);key_at(14,0,False);settle()
  assert b'\xa6\x51\xf7' not in trace()[offset:]
  key_at(14,0,True);step(1250);key_at(14,0,False);settle()
  assert b'\xa6\x51\xf7' in trace()[offset:]
  selector(0);assert slot()==0;settle()
  # An unresponsive UART cannot block the screen, matrix, or selector.
  m.write32(HOST+0x48,1);selector(1)
  before=frames();step(100);assert frames()>before
  selector(0);assert slot()==0
  assert m.read32(HOST+8)==0
  return dict(status='passed',candidate_sha256=hashlib.sha256(Path(image).read_bytes()).hexdigest(),
   uart_bytes=m.read32(HOST+0x40),hardware_writes=False,real_arm_image=True,function_stubs=[],
   no_usb_startup=True,stock_framing=True,bluetooth_press_and_release=True,bluetooth_caps_ctrl_swap=True,
   release_before_switch=True,report_ack_timeout_is_not_rf_disconnect=True,wireless_idle_uart_and_first_key_without_usb=True,usb_cable_does_not_replace_wireless=True,
   unavailable_requests_preserve_route=True,physical_selector_clears_override=True,
   switching_never_pairs=True,fn_wheel_toggles_previous_bluetooth=True,separate_pair_confirmation=True,stuck_uart_bounded=True,
   limitations=['UART replies are explicitly injected by the test','No Bluetooth or receiver RF link is modeled','Physical pairing and selector power rails require hardware checks'])

def connection_order(image):
 for event_first in (True,False):
  with System(image) as m:
   m.until('keyboard_post_init_user');m.write32(HOST+0x204,0)
   m.until('housekeeping_task_user');m.advance(3);m.pump()
   def inject(packet):
    for byte in packet:m.write32(HOST+0x44,byte)
    m.advance(2);m.pump()
   assert m.read(m.symbols['waiting'],1)==b'\1'
   if event_first:
    inject(bytes([0x5b,0x32,0x8d]))
    assert m.read(m.symbols['connected'],1)==b'\1','Connection event before ACK was lost'
    inject(b'\x61\x0d\x0a')
   else:
    inject(b'\x61\x0d\x0a')
    assert m.read(m.symbols['connected'],1)==b'\0','Generic command ACK claimed a connection'
    inject(bytes([0x5a,0,0x5a]))
    assert m.read(m.symbols['connected'],1)==b'\1','Stock host-status packet did not mark the link'
   inject(bytes([0x5b,0x33,0x8e]))
   assert m.read(m.symbols['connected'],1)==b'\0','Disconnect event stayed connected'
 return dict(connection_event_before_ack=True,ack_alone_is_not_connected=True,host_status_marks_connected=True,disconnect_clears_state=True)


if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('image',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 result=run(a.image);result['connection_order']=connection_order(a.image);a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
