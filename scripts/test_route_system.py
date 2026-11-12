"""Real ARM preference writes and cold-start selector routing; no physical USB."""
import argparse,hashlib,json,struct,tempfile,zlib
from pathlib import Path
from system_emulator import System,HOST
from test_system_emulator import enumerate_usb
BASE=0x3e800
def run(image):
 with System(image) as m:
  enumerate_usb(m)
  def step(ms=60):
   for at in range(0,ms,5):
    m.write32(HOST+0x30,0);m.advance(min(5,ms-at));m.pump()
    if m.read(m.symbols['waiting'],1)==b'\1':
     for value in b'\x61\x0d\x0a':m.write32(HOST+0x44,value)
     m.advance(1);m.pump()
  def uart(a,b):
   for value in [a,b,(a+b)&255]:m.write32(HOST+0x44,value)
   step()
  def key(row,col,down):m.write32(HOST+0x100+row*4,(1<<col) if down else 0);step()
  def choose(row):key(11,5,True);key(row,1,True);key(row,1,False);key(11,5,False)
  m.write32(HOST+0x204,1<<17);step(160);uart(0x5b,0x32)
  choose(2);assert m.read(m.symbols['active_slot'],1)==b'\2';uart(0x5b,0x32);step(1800)
  journal=m.read(BASE,2048);assert journal[:4]==b'F75R';assert struct.unpack_from('<I',journal,8)[0]==2
  assert zlib.crc32(journal[:12])==struct.unpack_from('<I',journal,12)[0]
  assert m.read(0x38000,8192)==b'\xff'*8192,'Remembering Bluetooth saved unrelated settings'
  programs=m.read32(HOST+0x5c);step(1200);assert m.read32(HOST+0x5c)==programs,'Duplicate connection wore flash'
  choose(3);assert m.read(m.symbols['active_slot'],1)==b'\3';step(2300)
  assert m.read(BASE,2048)==journal,'Failed Bluetooth request replaced the last successful slot'
  assert m.read32(HOST+0x60)==0
 with tempfile.TemporaryDirectory() as directory:
  data=bytearray(image.read_bytes());data[BASE:BASE+2048]=journal;path=Path(directory)/'remembered.bin';path.write_bytes(data)
  for mode,expected in [('bluetooth',2),('usb',0),('receiver',4)]:
   with System(path,symbols_file=image.with_suffix('.elf')) as m:
    m.until('keyboard_post_init_user')
    m.write32(HOST+0x204,(1<<17)|((1<<2) if mode=='usb' else 0))
    if mode=='receiver':m.write32(HOST+0x200,(1<<2)|(1<<3))
    m.until('housekeeping_task_user');assert m.read(m.symbols['active_slot'],1)==bytes([expected]),mode
 return dict(status='passed',candidate_sha256=hashlib.sha256(image.read_bytes()).hexdigest(),real_arm_image=True,successful_bt2_remembered=True,failed_bt3_does_not_replace=True,cold_boot_bt2=True,usb_and_receiver_selector_respected=True,duplicate_connections_do_not_write=True,unrelated_settings_untouched=True,protected_code_untouched=True,physical_hardware_tested=False)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('image',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args();r=run(a.image);a.output.write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r))
