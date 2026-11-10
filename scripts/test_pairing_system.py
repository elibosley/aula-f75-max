#!/usr/bin/env python3
"""Exercise pairing status against delayed UART events in the actual ARM image.

UART replies are injected explicitly. No RF pairing or bond persistence is claimed.
"""
import argparse, hashlib, json, struct
from pathlib import Path
from system_emulator import System, HOST


def run(image,late=False):
 with System(image) as m:
  m.until('keyboard_post_init_user');m.write32(HOST+0x204,0)
  m.until('housekeeping_task_user')
  def step(ms=5):
   for elapsed in range(0,ms,2):
    m.write32(HOST+0x30,0);m.advance(min(2,ms-elapsed));m.pump()
    if m.read(m.symbols['waiting'],1)==b'\1':
     for byte in b'\x61\x0d\x0a':m.write32(HOST+0x44,byte)
     m.advance(1);m.pump()
  def inject(packet):
   for byte in packet:m.write32(HOST+0x44,byte)
   step(4)
  def trace():return m.read(0x61000000,m.read32(HOST+0x40))
  def phase():return m.read(m.symbols['state']+134,1)[0]
  keymap=struct.unpack('<90H',m.read(m.symbols['keymaps'],180))
  def key(index,down):
   row,col=divmod(index,6)
   m.write32(HOST+0x100+row*4,(1<<col) if down else 0);step(25)
  step(50);inject(bytes.fromhex('5b328d'))
  assert m.read(m.symbols['connected'],1)==b'\1'
  key(71,True);key(keymap.index(0x13),True);key(keymap.index(0x13),False);key(71,False)
  assert phase()==1,'Fn+P did not request confirmation'
  offset=len(trace());m.write32(HOST+0x48,1)
  key(84,True);step(1250);key(84,False)
  assert phase()==2 and bytes.fromhex('a651f7') not in trace()[offset:]
  # A status from the old link arrives while the new command cannot be sent.
  inject(bytes.fromhex('5a005a'))
  assert phase()==2,'Old LED status dismissed pairing before its command was sent'
  assert m.read(m.symbols['connected'],1)==b'\0','Old link was reused for pairing'
  m.write32(HOST+0x48,0);step(50)
  assert bytes.fromhex('a651f7') in trace()[offset:]
  assert phase()==2,'Command ACK alone dismissed pairing'
  if late:
   # Model discovery/host UI taking longer than the keyboard's 30 s dialog.
   started=struct.unpack('<I',m.read(m.symbols['state']+120,4))[0]
   m.write(m.symbols['state']+120,struct.pack('<I',(started-30001)&0xffffffff));step(4)
   assert phase()==3,'Pairing timeout fixture did not enter the timeout state'
  inject(bytes.fromhex('5b328d'))
  assert phase()==0 and m.read(m.symbols['connected'],1)==b'\1','Connected radio retained the pairing timeout state' if late else 'Connection did not finish pairing'
  assert m.read32(HOST+8)==0
 return dict(status='passed',candidate_sha256=hashlib.sha256(Path(image).read_bytes()).hexdigest(),
             hardware_writes=False,old_link_before_pair_transmit_rejected=True,
             pairing_ack_is_not_connection=True,new_connection_finishes_dialog=True,
             physical_pairing_and_saved_bond='not_observed')


if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('image',type=Path);p.add_argument('--output',type=Path,required=True)
 a=p.parse_args();result=run(a.image);result['late_connection_clears_timeout']=run(a.image,late=True)['new_connection_finishes_dialog'];a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
