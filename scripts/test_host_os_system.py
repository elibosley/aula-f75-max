#!/usr/bin/env python3
"""OS hints through actual ARM USB, with explicit modeled radio connection events."""
import argparse,hashlib,json,struct
from pathlib import Path
from system_emulator import System,HOST
from test_system_emulator import enumerate_usb

def run(image):
 with System(image) as m:
  enumerate_usb(m)
  def step(ms=5):
   m.write32(HOST+0x30,0);m.advance(ms);m.pump()
   # A real USB host consumes reports even when the test does not inspect them.
   for ep in (1,4):
    for _ in range(12):
     if m.endpoint_in(ep) is None:break
  def inject(packet):
   for b in packet:m.write32(HOST+0x44,b)
   step(2)
  def settle():
   for _ in range(15):
    step(2)
    if m.read(m.symbols['waiting'],1)[0]:inject(b'\x61\x0d\x0a')
  def status():
   m.endpoint_out(3,b'F75ostat'+bytes(24));step();r=m.endpoint_in(2);assert r[:8]==b'F75pstat';return r
  def hint(slot,os,transaction,advance=True):
   packet=b'F75lhintHOSTOS!!'+bytes([slot,os,0,0])+struct.pack('<I',transaction)+bytes(8)
   m.endpoint_out(3,packet)
   if advance:step()
   return m.endpoint_in(2)
  def transaction():return struct.unpack_from('<I',status(),20)[0]
  step(400);s=status();assert s[18]==1 and s[10]==0
  assert hint(1,0,transaction())[8]==0
  # Select BT1 using the real switch scanner, then explicitly model its radio ACK/link.
  m.write32(HOST+0x200,(1<<10)|(1<<2)|(1<<3));m.write32(HOST+0x204,0);step(25);step(25);settle();inject(bytes.fromhex('5b328d'));settle()
  s=status();assert s[10]==1 and s[19]&1,s.hex();tx=transaction()
  m.write(m.symbols['state']+1,b'\1') # Windows profile fixture, while USB is a Mac.
  assert hint(2,0,tx)[8]==0
  assert hint(1,2,tx)[8]==0
  assert hint(1,0,tx+1)[8]==0
  assert m.read(m.symbols['state']+1,1)==b'\1'
  before=struct.unpack_from('<I',status(),24)[0]
  assert hint(1,0,tx)[8]==1;settle();s=status()
  assert s[11:16]==bytes([0,0,1,0,1]) and s[17]&2 and struct.unpack_from('<I',s,24)[0]==before+1,s.hex()
  assert s[16]==1,'OS hint changed Caps/Ctrl policy'
  # A manual Fn+M override must clear auto and prevent the helper changing it.
  keymap=struct.unpack('<90H',m.read(m.symbols['keymaps'],180))
  def key(index,down):
   row,col=divmod(index,6);m.write32(HOST+0x100+row*4,(1<<col) if down else 0);step(20)
  key(71,True);key(keymap.index(0x10),True);key(keymap.index(0x10),False);key(71,False);settle()
  s=status();assert not s[9]&2 and not s[17]&2 and s[12]==1,s.hex()
  assert hint(1,0,transaction())[8]==0 and status()[12]==1
  # Re-enable auto as a test fixture, then verify disconnect and deferred-route guards.
  m.write(m.symbols['state']+114,b'\x1f');inject(bytes.fromhex('5b338e'));assert hint(1,0,transaction())[8]==0
  inject(bytes.fromhex('5b328d'));settle();tx=transaction()
  m.poll_checkpoint='f75_host_os_hint'
  m.endpoint_out(3,b'F75lhintHOSTOS!!'+bytes([1,0,0,0])+struct.pack('<I',tx)+bytes(8))
  # Stop at the real apply function, after receive validation but before its
  # state check. This models the route changing while work is queued.
  m.write(m.symbols['state']+124,struct.pack('<I',tx+1));m.poll_checkpoint='housekeeping_task_user';step()
  reply=m.endpoint_in(2);assert reply[8]==1
  assert status()[12]==1,'Stale queued hint changed layout'
  assert m.read32(HOST+8)==0
 return {'status':'passed','candidate_sha256':hashlib.sha256(Path(image).read_bytes()).hexdigest(),'hardware_writes':False,'real_usb_hint_and_status':True,'only_active_wireless_host_changes':True,'manual_override_wins':True,'disconnected_and_stale_hints_rejected':True,'queued_hint_revalidated':True,'caps_ctrl_unchanged':True,'radio_link_is_modeled_not_RF':True}
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('image',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args();r=run(a.image);a.output.write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r))
