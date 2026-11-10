#!/usr/bin/env python3
"""Keep USB typing when a previously seen radio stops acknowledging selection.

The modeled radio omits replies. This is not a physical power-rail test.
"""
import argparse, hashlib, json, struct
from pathlib import Path
from system_emulator import System, HOST
from test_system_emulator import enumerate_usb


def run(image):
 with System(image) as m:
  enumerate_usb(m)
  def step(ms=25):
   m.write32(HOST+0x30,0);m.advance(ms);m.pump()
  def key(index, down):
   row,col=divmod(index,6)
   m.write32(HOST+0x100+row*4,(1<<col) if down else 0);step()
  # A valid historical packet establishes "seen", but no radio reply follows.
  for byte in bytes.fromhex('5b338e'):m.write32(HOST+0x44,byte)
  step();assert m.read(m.symbols['seen'],1)==b'\1'
  assert m.read(m.symbols['active_slot'],1)==b'\0'
  keymap=struct.unpack('<90H',m.read(m.symbols['keymaps'],180))
  key(71,True);key(keymap.index(0x1e),True);key(keymap.index(0x1e),False);key(71,False)
  step(150)
  assert m.read(m.symbols['active_slot'],1)==b'\0','Unanswered radio selection replaced working USB route'
  while m.endpoint_in(1) is not None:pass
  key(keymap.index(4),True)
  assert m.endpoint_in(1)==bytes([0,0,4,0,0,0,0,0]),'USB typing did not survive radio failure'
  key(keymap.index(4),False);assert m.endpoint_in(1)==bytes(8)
 return {'usb_preserved_after_radio_selection_timeout':True,'usb_typing_after_failure':True}


class Selection:
 def __init__(self,image):
  self.m=System(image);enumerate_usb(self.m)
  self.keymap=struct.unpack('<90H',self.m.read(self.m.symbols['keymaps'],180))
  for byte in bytes.fromhex('5b338e'):self.m.write32(HOST+0x44,byte)
  self.step(80,ack=True)
 def __enter__(self):return self
 def __exit__(self,*exc):self.m.close()
 def value(self,name):return self.m.read(self.m.symbols[name],1)[0]
 def trace(self):return self.m.read(0x61000000,self.m.read32(HOST+0x40))
 def step(self,ms=4,ack=False):
  for elapsed in range(0,ms,2):
   self.m.write32(HOST+0x30,0);self.m.advance(min(2,ms-elapsed));self.m.pump()
   if ack and self.value('waiting'):self.ack()
 def ack(self):
  for byte in b'\x61\x0d\x0a':self.m.write32(HOST+0x44,byte)
  self.m.advance(1);self.m.pump()
 def key(self,usage,down,ms=12):
  index=self.keymap.index(usage);row,col=divmod(index,6)
  self.m.write32(HOST+0x100+row*4,(1<<col) if down else 0);self.step(ms)
 def fn(self,down):
  self.m.write32(HOST+0x100+11*4,(1<<5) if down else 0);self.step(20)
 def select(self,slot):
  self.fn(True);self.key(0x1d+slot,True,20)
  assert self.value('active_slot')==0 and self.value('radio_switch_pending')==1
 def until_selector(self,slot,offset):
  value=0x30+slot;packet=bytes([0xa6,value,(0xa6+value)&255])
  for _ in range(60):
   if packet in self.trace()[offset:]:
    assert self.value('waiting');return
   if self.value('waiting'):self.ack()
   self.step(2)
  raise AssertionError('New selector packet was not transmitted')


def selection_cases(image):
 results={}
 # An older in-flight selector must not satisfy a new request, even if the
 # command bytes are identical. Only its own queue generation may commit.
 for next_slot in (1,2):
  with Selection(image) as f:
   start=len(f.trace());f.select(1);f.until_selector(1,start)
   f.key(0x1e,False);f.key(0x1d+next_slot,True)
   assert f.value('active_slot')==0 and f.value('radio_switch_pending')==1
   f.ack();f.step(2)
   assert f.value('active_slot')==0,'Older selection ACK committed the replacement request'
   assert f.value('radio_switch_pending')==1
   start=len(f.trace());f.until_selector(next_slot,start)
   assert f.value('active_slot')==0
   f.ack();f.step(4)
   assert f.value('active_slot')==next_slot and not f.value('radio_switch_pending')
   assert not f.value('connected'),'Transport ACK falsely claimed an RF connection'
  results['old_identical_ack_rejected' if next_slot==1 else 'only_latest_replacement_commits']=True
 # Fn+5 and physical selector movement cancel a queued software request.
 for physical in (False,True):
  with Selection(image) as f:
   start=len(f.trace());f.select(2);f.until_selector(2,start)
   if physical:
    f.m.write32(HOST+0x204,0);f.step(50)
    expected=1
   else:
    f.key(0x1f,False);f.key(0x22,True);expected=0
   assert f.value('active_slot')==expected and not f.value('radio_switch_pending')
   f.ack();f.step(20,ack=True)
   assert f.value('active_slot')==expected,'Canceled radio request committed later'
  results['physical_selector_cancels_pending' if physical else 'fn5_cancels_pending']=True
 # A UART that never becomes TX-ready must hit the independent wall deadline.
 with Selection(image) as f:
  f.m.write32(HOST+0x48,1);f.select(1);f.step(300)
  assert f.value('active_slot')==0 and not f.value('radio_switch_pending')
  results['stuck_uart_deadline_keeps_usb']=True
 return results


if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('image',type=Path);p.add_argument('--output',type=Path,required=True)
 a=p.parse_args();r={'candidate_sha256':hashlib.sha256(a.image.read_bytes()).hexdigest(),'hardware_writes':False}
 try:r.update({**run(a.image),**selection_cases(a.image)},status='passed')
 except Exception as e:r.update(status='failed',error=str(e));raise
 finally:a.output.write_text(json.dumps(r,indent=2)+'\n')
 print(json.dumps(r))
