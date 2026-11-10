#!/usr/bin/env python3
"""Qualify the exact recovery assembly through the captured ROM and USB stack."""
import argparse
import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import time
import uuid
from flash_keyboard import ROOT, STOCK, Rom, checksum, program
from system_emulator import System, USB, HOST


def build(out):
    tc=ROOT/'builddeps/arm-toolchain/bin'
    source=ROOT/'firmware/targets/f75max/recovery.S'
    subprocess.run([str(tc/'arm-none-eabi-gcc'),'-mcpu=cortex-m0','-mthumb','-nostdlib',
                    '-Wl,-Ttext=0x3e000','-Wl,-e,f75_enter_rom','-Wl,--defsym,_crt0_entry=0x8ee8',
                    str(source),'-o',str(out/'bridge.elf')],check=True)
    subprocess.run([str(tc/'arm-none-eabi-objcopy'),'-O','binary',str(out/'bridge.elf'),str(out/'bridge.bin')],check=True)
    syms={}
    for line in subprocess.check_output([str(tc/'arm-none-eabi-nm'),'-n',str(out/'bridge.elf')],text=True).splitlines():
        f=line.split()
        if len(f)==3:syms[f[2]]=int(f[0],16)
    stock=STOCK.read_bytes();stub=(out/'bridge.bin').read_bytes()
    assert stock[0x3e000:0x3e000+len(stub)]==b'\xff'*len(stub)
    image=bytearray(stock);struct.pack_into('<I',image,4,syms['f75_enter_rom']|1);image[0x3e000:0x3e000+len(stub)]=stub
    allowed=set(range(4,8))|set(range(0x3e000,0x3e000+len(stub)))
    assert all(a==b or i in allowed for i,(a,b) in enumerate(zip(stock,image)))
    path=out/'image.bin';path.write_bytes(image)
    return path,dict(image_sha256=hashlib.sha256(image).hexdigest(),checksum=f'{checksum(image):04x}',
                     rom_entry=hex(syms['f75_enter_rom']),source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                     diagnostic_behavior='Unconditional ROM handoff from reset; no keyboard application expected')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',action='store_true');args=p.parse_args()
    out=ROOT/'analysis/rom-handoff'/uuid.uuid4().hex;out.mkdir(parents=True)
    image,record=build(out)
    with System(image,symbols_file=out/'bridge.elf',factory_rom=True) as s:
        s.poll_checkpoint=0x1fff03bc;s.pump();s.pump(1<<31)
        descriptor=s.control(0x80,6,0x100,length=18)
        assert descriptor==bytes.fromhex('1201000200000040450c4071010100000001')
        assert s.read32(HOST+8)==0
        record['emulated_factory_usb_descriptor']=descriptor.hex();record['factory_rom_executed']=True
    record.update(stage='emulated',hardware_writes=False,started_at=datetime.datetime.now(datetime.timezone.utc).isoformat())
    path=out/'receipt.json'
    def save():
        t=path.with_suffix('.tmp');t.write_text(json.dumps(record,indent=2)+'\n');t.replace(path)
    save();print('ROM handoff receipt:',path,flush=True)
    if not args.run:return
    lock=os.open(ROOT/'.runtime/keyboard-flash.lock',os.O_RDWR|os.O_NOFOLLOW);fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    rom=None
    try:
        rom=Rom(0x0c45,0x800a);rom.write(bytes.fromhex('aa42895aff7162cc')+bytes(56));time.sleep(.1)
        record['hardware_writes']=True;program(rom,image.read_bytes(),0xb9d0,record,save)
        rom.command(7);rom.close();rom=None
        # Do not overwrite return-user opcode 7 with another SET_REPORT while
        # its delayed reset/disconnect is still being processed.
        time.sleep(3)
        rom=Rom(0x0c45,0x7140)
        identity=rom.identify();measured=rom.sum()
        assert measured==checksum(image.read_bytes()),'Returned ROM has another application checksum'
        record['hardware_rom_return']=dict(identity=identity,checksum=f'{measured:04x}',pid='7140',settling_seconds=3)
        record['stage']='hardware_handoff_returned';save()
        restore=dict(erase_requested=False,security_restore_requested=False);record['restore']=restore
        program(rom,STOCK.read_bytes(),measured,restore,save);rom.command(7)
        record['stage']='stock_restored';save();print('Factory handoff passed; stock restored.',flush=True)
    except Exception as error:
        record['error']=str(error);save();raise
    finally:
        if rom:rom.close()
        os.close(lock)


if __name__=='__main__':main()
