#!/usr/bin/env python3
"""Check the stock idle-command oracle and qualification image wake ordering.

Injected UART acknowledgments do not emulate radio sleep or establish savings.
"""
import argparse,hashlib,json,struct
from pathlib import Path
from system_emulator import System,HOST
from test_system_emulator import enumerate_usb

def stock_oracle(stock):
 from unicorn import Uc,UC_ARCH_ARM,UC_MODE_THUMB,UC_MODE_MCLASS,UC_HOOK_CODE
 from unicorn.arm_const import UC_ARM_REG_SP,UC_ARM_REG_LR
 data=stock.read_bytes();assert hashlib.sha256(data).hexdigest()=='a7d458754f3cc3aed7c8956f854148e081bc63f524da230a8ea8d3b3b3a4b5e9'
 cpu=Uc(UC_ARCH_ARM,UC_MODE_THUMB|UC_MODE_MCLASS);cpu.mem_map(0,0x40000);cpu.mem_write(0,data);cpu.mem_map(0x20000000,0x8000)
 cpu.mem_write(0x200000e4,b'\x01');cpu.mem_write(0x200000e6,b'\x01');cpu.mem_write(0x200000f1,b'\x01');cpu.mem_write(0x20000105,b'\x55')
 cpu.reg_write(UC_ARM_REG_SP,0x20007000);cpu.reg_write(UC_ARM_REG_LR,0x3ff01);packets=[]
 def hook(cpu,address,size,context):
  if address==0x12f00:
   length=cpu.mem_read(0x20000279,1)[0];packets.append(bytes(cpu.mem_read(0x200025da,length)));cpu.emu_stop()
 cpu.hook_add(UC_HOOK_CODE,hook);cpu.emu_start(0x45e5,0x3ff00,count=10000)
 assert packets==[bytes.fromhex('a655fb')],packets
 return dict(stock_sha256=hashlib.sha256(data).hexdigest(),dispatcher_address='0x45e4',payload_address='0x20000105',transmit_packet=packets[0].hex(),radio_power_state_measured=False)

def stock_wake_oracle(stock):
 from unicorn import Uc,UC_ARCH_ARM,UC_MODE_THUMB,UC_MODE_MCLASS,UC_HOOK_CODE
 from unicorn.arm_const import UC_ARM_REG_SP,UC_ARM_REG_LR,UC_ARM_REG_PC,UC_ARM_REG_R0
 data=stock.read_bytes();assert hashlib.sha256(data).hexdigest()=='a7d458754f3cc3aed7c8956f854148e081bc63f524da230a8ea8d3b3b3a4b5e9'
 cpu=Uc(UC_ARCH_ARM,UC_MODE_THUMB|UC_MODE_MCLASS);cpu.mem_map(0,0x40000);cpu.mem_write(0,data);cpu.mem_map(0x20000000,0x8000)
 for address,value in [(0x200000e4,1),(0x200000e6,1),(0x200000eb,1),(0x2000005f,1)]:cpu.mem_write(address,bytes([value]))
 cpu.reg_write(UC_ARM_REG_SP,0x20007000);cpu.reg_write(UC_ARM_REG_LR,0x3ff01)
 cpu.emu_start(0x45e5,0x3ff00,count=10000)
 assert cpu.mem_read(0x200000ef,1)==b'\1' and cpu.mem_read(0x2000005f,1)==b'\1','Stock did not retain first key while requesting wake'
 packets=[];delays=[];ack_snapshots=[]
 def hook(cpu,address,size,context):
  if address==0x12f00:
   packets.append(bytes(cpu.mem_read(0x200025da,cpu.mem_read(0x20000279,1)[0])));cpu.reg_write(UC_ARM_REG_PC,cpu.reg_read(UC_ARM_REG_LR))
  elif address==0x7d98:
   delays.append(cpu.reg_read(UC_ARM_REG_R0));cpu.reg_write(UC_ARM_REG_PC,cpu.reg_read(UC_ARM_REG_LR))
  elif address==0x45bc:ack_snapshots.append(address)
  elif address==0x4934:cpu.emu_stop()
 cpu.hook_add(UC_HOOK_CODE,hook);cpu.reg_write(UC_ARM_REG_SP,0x20007000);cpu.reg_write(UC_ARM_REG_LR,0x3ff01)
 cpu.emu_start(0x45e5,0x3ff00,count=10000)
 assert packets==[bytes.fromhex('a600a6')] and delays==[3] and not ack_snapshots,(packets,delays,ack_snapshots)
 assert cpu.mem_read(0x2000005f,1)==b'\1','Wake consumed the pending key'
 return dict(stock_wake_packet=packets[0].hex(),settle_milliseconds=3,first_key_retained=True,ack_retry_snapshot_armed=False,hardware_tested=False)

def run(image, disabled=False):
 with System(image) as m:
  m.until('housekeeping_task_user');auto_ack=True
  def waiting():return bool(m.read(m.symbols['waiting'],1)[0])
  def step(ms=10):
   for elapsed in range(0,ms,2):
    m.write32(HOST+0x30,0);m.advance(min(2,ms-elapsed));m.pump()
    if auto_ack and waiting():
     for byte in b'\x61\x0d\x0a':m.write32(HOST+0x44,byte)
     m.advance(1);m.pump()
  def inject(data):
   for byte in data:m.write32(HOST+0x44,byte)
   step(2)
  def trace():return m.read(0x61000000,m.read32(HOST+0x40))
  def phase():return m.read(m.symbols['radio_sleep_phase'],1)[0]
  def age():
   now=m.read32(m.symbols['state']+116)
   m.write(m.symbols['state']+116,struct.pack('<I',(now-181000)&0xffffffff));step(220)
  keymap=struct.unpack('<90H',m.read(m.symbols['keymaps'],180))
  def key(usage,down):
   index=keymap.index(usage);row,col=divmod(index,6);m.write32(HOST+0x100+row*4,(1<<col) if down else 0);step(20)
  step(120);assert b'\xa6\x55\xfb' not in trace(),'USB-selected route requested radio sleep'
  m.write32(HOST+0x204,0);step(120);inject(bytes.fromhex('5b328d'));step(120)
  assert m.read(m.symbols['connected'],1)==b'\1'
  assert b'\xa6\x55\xfb' not in trace(),'Active typing route requested radio sleep'
  enumerate_usb(m)
  def control_trace(clear=False):
   payload=b'CLRTRACE'+bytes(16) if clear else bytes(24)
   m.endpoint_out(3,b'F75Ltrce'+payload);step(5);reply=m.endpoint_in(2)
   assert reply and reply[:8]==b'F75Ltrce';return reply[8:]
  assert control_trace(True)==bytes(24)
  inject(bytes.fromhex('5ae03a'));masked=control_trace()
  assert masked[12:15]==bytes.fromhex('5a0000'),'Encoded host payload was retained'
  # Close the deliberately opened status frame through its real neutral symbol.
  inject(bytes.fromhex('5a005a'))
  assert control_trace(True)==bytes(24)
  if disabled:
   offset=len(trace());age();step(250)
   assert bytes.fromhex('a655fb') not in trace()[offset:] and phase()==0
   return dict(status='passed',candidate_sha256=hashlib.sha256(image.read_bytes()).hexdigest(),hardware_writes=False,radio_sleep_disabled_by_default=True)
  # A completed settings read leaves no session. The fixture changes no firmware
  # function: age only the real activity timestamp to reach Balanced sleep.
  offset=len(trace());now=m.read32(m.symbols['state']+116)
  m.write(m.symbols['state']+116,struct.pack('<I',(now-181000)&0xffffffff))
  inject(bytes.fromhex('610d0a'));assert phase()==0,'An old ACK completed an unsent sleep request'
  step(60);assert phase()==0,'Quiet interval was bypassed'
  step(160);data=trace()[offset:]
  assert data.count(bytes.fromhex('a655fb'))==1,data.hex();assert phase()==2,phase()
  step(250);assert trace()[offset:].count(bytes.fromhex('a655fb'))==1,'Idle command repeated'
  idle_trace=control_trace();assert idle_trace[20:23]==bytes.fromhex('a655fb') and idle_trace[12:15]==bytes.fromhex('610d0a')
  # No pairing, slot reset, or overwritten first key: wake selection precedes
  # the actual keyboard report and its key-up, using the existing bound slot.
  offset=len(trace());key(4,True);key(4,False);step(40);data=trace()[offset:]
  wake=bytes.fromhex('a600a6');down=bytes.fromhex('a10000040000000000a5');up=bytes.fromhex('a10000000000000000a1')
  assert wake in data and down in data and up in data,data.hex()
  assert data.index(wake)<data.index(down)<data.rindex(up);assert bytes.fromhex('a651f7') not in data
  assert phase()==0 and m.read(m.symbols['active_slot'],1)==b'\1'
  retained=control_trace();assert retained[:23]==idle_trace[:23] and retained[23]==idle_trace[23]|128,'Wake overwrote the retained idle exchange'
  assert control_trace(True)==bytes(24)
  # Held keys block sleep even when an artificial old activity timestamp is
  # injected. Real held-input state and release ordering must remain intact.
  key(4,True);offset=len(trace());age();assert bytes.fromhex('a655fb') not in trace()[offset:]
  key(4,False);step(120)
  # A timed-out sleep request has at most the existing three transmissions.
  # It latches failure rather than continuously retrying on every main loop.
  auto_ack=False;offset=len(trace());age();step(300);data=trace()[offset:]
  assert data.count(bytes.fromhex('a655fb'))==3,data.hex();assert phase()==4
  step(300);assert trace()[offset:].count(bytes.fromhex('a655fb'))==3
  inject(bytes.fromhex('610d0a'));assert phase()==4,'Late ACK fabricated a completed sleep transition'
  late=control_trace();assert late[12:15]==bytes.fromhex('610d0a') and late[15]&7==4 and not late[15]&8
  auto_ack=True;offset=len(trace());key(4,True);key(4,False);step(40);data=trace()[offset:]
  assert wake in data and down in data and up in data and data.index(wake)<data.index(down),'Uncertain sleep ACK lost wake-before-report ordering'
  m.write32(HOST+0x200,1<<3);m.write32(HOST+0x204,1<<2);step(100);inject(bytes.fromhex('5b328d'));step(120)
  offset=len(trace());age();assert bytes.fromhex('a655fb') not in trace()[offset:],'Unqualified receiver idle command was sent' 
  assert m.read32(HOST+8)==0
 return dict(status='passed',candidate_sha256=hashlib.sha256(image.read_bytes()).hexdigest(),hardware_writes=False,stock_command='a655fb',sleep_request_one_per_idle_period=True,first_key_and_release_preserved=True,stock_wake_preamble_without_repairing=True,stale_ack_before_transmit_rejected=True,uncertain_sleep_ack_still_wakes_before_first_report=True,receiver_sleep_not_enabled=True,held_keys_block_request=True,missing_ack_bounded_to_three_transmissions=True,retained_control_trace_preserves_idle_and_late_ack=True,encoded_host_payloads_not_retained=True,rf_sleep_measured=False,deep_mcu_sleep=False,physical_wake_qualification='pending')

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('image',type=Path);p.add_argument('--stock',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--expect-disabled',action='store_true');a=p.parse_args();r=run(a.image,a.expect_disabled);r['stock_oracle']=stock_oracle(a.stock);r['stock_wake_oracle']=stock_wake_oracle(a.stock);a.output.write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r))
