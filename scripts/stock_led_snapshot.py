#!/usr/bin/env python3
"""Fixed, read-only LED register banks in stock's unchanged USB callback.
Run temporarily installs the bounded wrapper, captures banks, and restores stock.
"""
import argparse,datetime,fcntl,hashlib,json,os,secrets,struct,subprocess,time,uuid
from pathlib import Path
from flash_keyboard import ROOT,STOCK,Rom,checksum,program
from stock_rom_diagnostic import branch_link,StockUsb,CALL,BUFFER,STATUS
# The original 216-byte reader fit below stock data at 0x3e110.
# This expanded table must live elsewhere. No stock literals reference 0x2e000.
HOOK=0x2e000
from emulate import Firmware
BANKS=[
 [0x40060004,0x40060008,0x4006000c,0x40060010,0x4005e000,0x4005e004,0x40044000,0x40046000,0x40048000,0x4004a000,0x40044004,0x40046004],
 [0x40042000+x for x in [0,4,8,12,16,20,24,28,32,36]]+[0x40048004,0x4004a004],
 *[[base+x for x in [0,4,8,12,16,20,32,36,40,44,68,152]] for base in [0x40000000]],
 [0x40002000+x for x in [0,4,8,12,16,20,24,80,148,152,160,164]],
 [0x40004000+x for x in [0,4,8,12,16,20,32,36,40,44,68,152]],
 [0x40006000+x for x in [0,4,8,12,16,20,32,36,68,148,152,176]],
 [base+x for base in [0x40044000,0x40046000,0x40048000,0x4004a000] for x in [4,44,48]],
 [0x40002020+x*4 for x in range(12)]
]
assert len(BANKS)==8 and all(len(b)==12 for b in BANKS)
SOURCE='''.syntax unified
.cpu cortex-m0
.thumb
.text
.balign 4
.global stock_led_hook
.thumb_func
stock_led_hook:
 push {r3,r4,r5,r6,r7,lr}
 ldr r4,=0x20001308
 ldrb r0,[r4,#0x12]
 cmp r0,#2
 bne original
 ldr r0,[r4,#0x14]
 ldr r1,=0x53353746
 cmp r0,r1
 bne original
 ldr r0,[r4,#0x1c]
 cmp r0,#8
 bhs original
 ldr r7,=registers
 movs r1,#48
 muls r0,r1
 adds r7,r7,r0
 mov r5,r4
 adds r5,#0x24
 movs r6,#12
copy:
 ldr r0,[r7]
 adds r7,#4
 ldr r0,[r0]
 str r0,[r5]
 adds r5,#4
 subs r6,#1
 bne copy
 movs r0,#48
 str r0,[r4,#0x20]
 ldr r0,=0x54353746
 str r0,[r4,#0x14]
 movs r0,#0
 strb r0,[r4,#0x12]
original:
 pop {r3,r4,r5,r6,r7}
 pop {r0}
 mov lr,r0
 ldr r0,=0x18ab
 bx r0
.balign 4
registers:
'''+''.join(' .word '+','.join(hex(x) for x in bank)+'\n' for bank in BANKS)+'.ltorg\n'
def prepare(out):
 stock=STOCK.read_bytes();assert hashlib.sha256(stock).hexdigest()=='a7d458754f3cc3aed7c8956f854148e081bc63f524da230a8ea8d3b3b3a4b5e9'
 source=out/'hook.S';source.write_text(SOURCE);tc=ROOT/'builddeps/arm-toolchain/bin'
 subprocess.run([str(tc/'arm-none-eabi-gcc'),'-mcpu=cortex-m0','-mthumb','-nostdlib',f'-Wl,-Ttext={HOOK:#x}','-Wl,-e,stock_led_hook',str(source),'-o',str(out/'hook.elf')],check=True)
 subprocess.run([str(tc/'arm-none-eabi-objcopy'),'-O','binary',str(out/'hook.elf'),str(out/'hook.bin')],check=True)
 hook=(out/'hook.bin').read_bytes();assert len(hook)<=512 and stock[HOOK:HOOK+len(hook)]==b'\xff'*len(hook)
 assert stock[CALL:CALL+4]==branch_link(CALL,0x18aa)
 image=bytearray(stock);image[CALL:CALL+4]=branch_link(CALL,HOOK);image[HOOK:HOOK+len(hook)]=hook
 assert image[:0xc0]==stock[:0xc0] and image[0x18aa:0x190c]==stock[0x18aa:0x190c] and image[-4:]==stock[-4:]
 for bank in range(10):
  fw=Firmware(bytes(image),stubs=[0x18aa]);request=b'F75Stest'+struct.pack('<II',bank,0)+bytes(48);fw.cpu.mem_write(BUFFER,request);fw.byte(STATUS,2)
  if bank<8:
   values=[0x81230000+i for i in range(12)]
   for address,value in zip(BANKS[bank],values):fw.word(address,value)
  fw.run(HOOK);response=bytes(fw.cpu.mem_read(BUFFER,64))
  if bank<8:assert response[:16]==b'F75Ttest'+struct.pack('<II',bank,48) and response[16:]==struct.pack('<12I',*values)
  else:assert response==request
  assert not fw.writes,'register reader changed a peripheral'
 fw=Firmware(bytes(image),stubs=[0x18aa]);boot=bytes.fromhex('aa42895aff7162cc')+bytes(56);fw.cpu.mem_write(BUFFER,boot);fw.byte(STATUS,2);fw.run(HOOK);assert bytes(fw.cpu.mem_read(BUFFER,64))==boot
 (out/'image.bin').write_bytes(image);return bytes(image)
def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--run',action='store_true');args=parser.parse_args()
 out=ROOT/'analysis/stock-led-snapshot'/uuid.uuid4().hex;out.mkdir(parents=True);image=prepare(out)
 record=dict(started_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),image_sha256=hashlib.sha256(image).hexdigest(),image_checksum=f'{checksum(image):04x}',hook_bytes=len((out/'hook.bin').read_bytes()),cpu_checks='all 8 banks, rejected banks, unchanged boot command, zero peripheral writes',stage='prepared',hardware_writes=False)
 def save():
  p=out/'receipt.json';t=p.with_suffix('.tmp');t.write_text(json.dumps(record,indent=2)+'\n');t.replace(p)
 save();print('LED snapshot receipt: '+str(out/'receipt.json'),flush=True)
 if not args.run:return
 lock=os.open(ROOT/'.runtime/keyboard-flash.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600);fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);rom=None;device=None;installed=False
 try:
  rom=Rom(0x0c45,0x800a);rom.write(bytes.fromhex('aa42895aff7162cc')+bytes(56));time.sleep(.1);record['hardware_writes']=True
  program(rom,image,0xb9d0,record,save);rom.command(7);installed=True;rom.close();rom=None;time.sleep(1)
  deadline=time.monotonic()+6
  while time.monotonic()<deadline:
   try:device=StockUsb();break
   except RuntimeError:time.sleep(.2)
  if device is None:raise RuntimeError('Stock diagnostic application did not become ready')
  snapshots=[]
  for repeat in range(2):
   banks=[]
   for bank in range(8):
    nonce=secrets.token_bytes(4);response=device.exchange(b'F75S'+nonce+struct.pack('<II',bank,0)+bytes(48));assert response[:3]==b'F75' and response[3] in (84,255) and response[4:16]==nonce+struct.pack('<II',bank,48), response[:16].hex()
    values=struct.unpack_from('<12I',response,16);banks.append({hex(a):hex(v) for a,v in zip(BANKS[bank],values)})
   snapshots.append(banks)
  record['snapshots']=snapshots;record['stage']='captured';save();print(json.dumps(snapshots[0],indent=2),flush=True)
 finally:
  if device:device.close()
  if rom:rom.close()
  if installed:
   restore=Rom(0x0c45,0x800a)
   try:
    restore.write(bytes.fromhex('aa42895aff7162cc')+bytes(56));time.sleep(.1);sub=dict(erase_requested=False,security_restore_requested=False);record['restore']=sub
    program(restore,STOCK.read_bytes(),checksum(image),sub,save);restore.command(7);record['stage']='stock_restored';save();print('Stock restored.',flush=True)
   finally:restore.close()
  os.close(lock)
if __name__=='__main__':main()
