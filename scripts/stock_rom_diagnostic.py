#!/usr/bin/env python3
"""Build/test a tiny bounded ROM-reader wrapper around the untouched stock USB callback."""
import argparse
import array
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
from emulate import Firmware, STOP
from unicorn import UC_HOOK_CODE
from unicorn.arm_const import *

STOCK_SHA='a7d458754f3cc3aed7c8956f854148e081bc63f524da230a8ea8d3b3b3a4b5e9'
HOOK=0x3e000
CALL=0xf64
BUFFER=0x2000131c
STATUS=0x2000131a


def sha(data): return hashlib.sha256(data).hexdigest()


def branch_link(source, target):
    delta=target-(source+4)
    assert delta%2==0 and -(1<<24)<=delta<(1<<24)
    imm=delta & ((1<<25)-1); s=(imm>>24)&1; i1=(imm>>23)&1; i2=(imm>>22)&1
    j1=(~(i1^s))&1; j2=(~(i2^s))&1
    return struct.pack('<HH',0xf000|(s<<10)|((imm>>12)&1023),0xd000|(j1<<13)|(j2<<11)|((imm>>1)&2047))


def assemble(out):
    stock=STOCK.read_bytes(); assert sha(stock)==STOCK_SHA
    tc=ROOT/'builddeps/arm-toolchain/bin'
    source=ROOT/'firmware/diagnostics/stock_rom_read.S'
    subprocess.run([str(tc/'arm-none-eabi-gcc'),'-mcpu=cortex-m0','-mthumb','-nostdlib',
                    '-Wl,-Ttext=0x3e000','-Wl,-e,stock_rom_hook',str(source),'-o',str(out/'hook.elf')],check=True)
    subprocess.run([str(tc/'arm-none-eabi-objcopy'),'-O','binary',str(out/'hook.elf'),str(out/'hook.bin')],check=True)
    hook=(out/'hook.bin').read_bytes(); assert len(hook)<512
    assert stock[CALL:CALL+4]==branch_link(CALL,0x18aa)
    assert stock[HOOK:HOOK+len(hook)]==b'\xff'*len(hook)
    image=bytearray(stock); image[CALL:CALL+4]=branch_link(CALL,HOOK); image[HOOK:HOOK+len(hook)]=hook
    allowed=set(range(CALL,CALL+4))|set(range(HOOK,HOOK+len(hook)))
    changes={i for i,(a,b) in enumerate(zip(stock,image)) if a!=b}; assert changes<=allowed
    assert image[:0xc0]==stock[:0xc0] and image[0x18aa:0x190c]==stock[0x18aa:0x190c]
    assert image[-4:]==stock[-4:]
    (out/'image.bin').write_bytes(image)
    return bytes(image),dict(stock_sha256=STOCK_SHA,image_sha256=sha(image),image_checksum=f'{checksum(image):04x}',
                            source_sha256=sha(source.read_bytes()),hook_bytes=len(hook),changed_bytes=len(changes),
                            vectors_unchanged=True,stock_boot_command_code_unchanged=True,
                            allowed_changed_ranges=[[CALL,CALL+4],[HOOK,HOOK+len(hook)]])


def cpu_checks(image):
    rom=bytes((i*17+23)&255 for i in range(4096)); cases=[]
    requests=[(0,48),(4048,48),(4080,16),(4095,1),(4096,1),(0,0),(0,49),(0xffffffff,48),(4090,48)]
    for offset,length in requests:
        fw=Firmware(image,stubs=[0x18aa]);fw.cpu.mem_map(0x1fff0000,4096);fw.cpu.mem_write(0x1fff0000,rom)
        request=b'F75Rtest'+struct.pack('<II',offset,length)+bytes(48)
        fw.cpu.mem_write(BUFFER,request);fw.byte(STATUS,2)
        fw.run(HOOK)
        valid=0<length<=48 and offset<=4096 and length<=4096-offset
        response=bytes(fw.cpu.mem_read(BUFFER,64))
        if valid:
            assert response[:16]==b'F75Dtest'+struct.pack('<II',offset,length)
            assert response[16:]==rom[offset:offset+length]+bytes(48-length)
            assert fw.byte(STATUS)==0
        else:assert response==request and fw.byte(STATUS)==2
        assert fw.calls and fw.calls[-1]['address']==0x18aa
        assert all(w['address']<0x40000000 for w in fw.writes), 'diagnostic wrote a peripheral'
        cases.append(dict(offset=offset,length=length,accepted=valid))
    for request in [bytes.fromhex('aa42895aff7162cc')+bytes(56),b'unknown!'+bytes(56)]:
        fw=Firmware(image,stubs=[0x18aa]);fw.cpu.mem_write(BUFFER,request);fw.byte(STATUS,2);fw.run(HOOK)
        assert bytes(fw.cpu.mem_read(BUFFER,64))==request and fw.byte(STATUS)==2
    fw=Firmware(image,stubs=[0x18aa]);fault=bytes(range(48))
    fw.cpu.mem_write(0x20007e00,fault);fw.cpu.mem_write(BUFFER,b'F75Ftest'+bytes(56));fw.byte(STATUS,2);fw.run(HOOK)
    assert bytes(fw.cpu.mem_read(BUFFER+16,48))==fault and fw.byte(STATUS)==0
    # Execute the patched BL in its stock call context; the original callback
    # is the only stub. It must return to the instruction after that same BL.
    fw=Firmware(image,stubs=[0x18aa]);fw.byte(STATUS,0)
    def returned(cpu,address,size,data):
        if address==CALL+4:
            fw.completed=True;cpu.emu_stop()
    fw.cpu.hook_add(UC_HOOK_CODE,returned)
    fw.run(CALL)
    return dict(status='passed',rom_reads=cases,vendor_boot_command_unchanged=True,
                unknown_reports_unchanged=True,patched_bl_returns=True,peripheral_writes=False,
                limitation='USB callback transport still requires hardware verification')


class StockUsb:
    def __init__(self):
        self.rom=Rom(0x0c45,0x800a)
        try:
            # macOS may retain the application's cached PID while the ROM is
            # still running. Query the live descriptor, not cached identity.
            data=array.array('B',bytes(18))
            n=self.rom.backend.ctrl_transfer(self.rom.handle,0x80,6,0x0100,0,data,250)
            if n!=18 or bytes(data[8:14])!=bytes.fromhex('450c0a801001'):
                raise RuntimeError('Live stock application descriptor is not ready')
            report=array.array('B',bytes(64))
            if self.rom.backend.ctrl_transfer(self.rom.handle,0xa1,1,0x0300,0,report,250)!=64:
                raise RuntimeError('Stock feature endpoint is not ready')
        except Exception:
            self.rom.close();raise
    def exchange(self,request):
        self.rom.write(request)
        data=array.array('B',bytes(64))
        n=self.rom.backend.ctrl_transfer(self.rom.handle,0xa1,1,0x0300,0,data,1500)
        if n!=64: raise RuntimeError(f'Stock feature report returned {n} bytes')
        return bytes(data)
    def close(self):self.rom.close()


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--run',action='store_true');args=ap.parse_args()
    out=ROOT/'analysis/stock-rom-diagnostic'/uuid.uuid4().hex;out.mkdir(parents=True)
    image,record=assemble(out);record['cpu_checks']=cpu_checks(image)
    record.update(started_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),hardware_writes=False,stage='prepared')
    path=out/'receipt.json'
    def save():
        tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(record,indent=2)+'\n');tmp.replace(path)
    save();print('Stock ROM diagnostic:',path,flush=True)
    if not args.run:return
    lock=os.open(ROOT/'.runtime/keyboard-flash.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    device=None
    try:
        device=Rom(0x0c45,0x800a)
        device.write(bytes.fromhex('aa42895aff7162cc')+bytes(56));time.sleep(.1)
        record['hardware_writes']=True
        program(device,image,0xb9d0,record,save);device.command(7);device.close();device=None
        # The old PID/descriptor may remain cached before the disconnect.
        # Permit that transition before admitting the next application handle.
        time.sleep(1)
        deadline=time.monotonic()+6
        while time.monotonic()<deadline:
            try:device=StockUsb();break
            except Exception:time.sleep(.2)
        if device is None:raise RuntimeError('Stock diagnostic did not return on USB; hardware recovery required')
        request=b'F75Stest'+bytes(56)
        snapshot=device.exchange(request)
        if snapshot[:3]!=b'F75' or snapshot[3] not in (ord('T'),255) or snapshot[4:8]!=b'test':
            raise RuntimeError(f'Register snapshot not acknowledged: {snapshot[:16].hex()}')
        names=['PLLCTRL','CSST','CLKCFG','AHBCP','IVTM','AHBCLKEN','GPIOB_DATA','GPIOB_MODE','GPIOB_CFG1','NVIC_ISER','SYSTICK_CTRL','USB_CFG']
        record['stock_registers']=dict(zip(names,[f'{v:08x}' for v in struct.unpack('<12I',snapshot[16:])]))
        save()
        dumps=[]
        record['stock_status_byte_ff_blocks']=0
        for attempt in range(2):
            data=bytearray()
            for offset in range(0,4096,48):
                count=min(48,4096-offset)
                response=device.exchange(b'F75Rtest'+struct.pack('<II',offset,count)+bytes(48))
                # Hardware shows the stock settings parser can replace byte 3
                # with its FF status. Nonce, offset, count and payload remain
                # intact. Validate those independently and compare full dumps.
                if (response[:3]!=b'F75' or response[3] not in (ord('D'),255)
                    or response[4:16]!=b'test'+struct.pack('<II',offset,count)):
                    raise RuntimeError('ROM block or nonce mismatch')
                record['stock_status_byte_ff_blocks']+=int(response[3]==255)
                data.extend(response[16:16+count])
            dumps.append(bytes(data));(out/f'boot-rom-{attempt+1}.bin').write_bytes(data)
        assert dumps[0]==dumps[1] and len(set(dumps[0]))>16,'ROM dump did not verify'
        sp,reset=struct.unpack_from('<II',dumps[0])
        assert 0x20000000<sp<=0x20008000 and 0x1fff0000<reset<0x1fff1000 and reset&1
        record['boot_rom_sha256']=sha(dumps[0]);record['boot_rom_bytes']=4096;record['two_reads_match']=True
        record['stage']='boot_rom_captured';save()
        device.close();device=None
    except Exception as error:
        record['error']=str(error);save()
        raise
    finally:
        if device:device.close()
        # Restore through the unchanged stock boot command whenever the app is
        # reachable. Never replace an unrecognized image or lower security.
        try:
            if record.get('program_verified'):
                rom=Rom(0x0c45,0x800a)
                try:
                    rom.write(bytes.fromhex('aa42895aff7162cc')+bytes(56));time.sleep(.1)
                    restore=dict(erase_requested=False,security_restore_requested=False);record['restore']=restore
                    program(rom,STOCK.read_bytes(),checksum(image),restore,save);rom.command(7)
                    record['stage']='stock_restored';save();print('Stock restored.',flush=True)
                finally:rom.close()
        finally:os.close(lock)


if __name__=='__main__':main()
