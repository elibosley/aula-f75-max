#!/usr/bin/env python3
"""Read one fixed SRAM diagnostic record via the stock wrapper, then restore stock."""
import argparse
import datetime
import fcntl
import json
import os
from pathlib import Path
import struct
import time
import uuid
from stock_rom_diagnostic import assemble, cpu_checks, StockUsb
from flash_keyboard import ROOT, STOCK, Rom, checksum, program


def wait_stock():
    deadline=time.monotonic()+8
    time.sleep(1)
    while time.monotonic()<deadline:
        try:return StockUsb()
        except Exception:time.sleep(.2)
    raise RuntimeError('Stock reader did not reach its feature endpoint')


def capture_from_rom(expected, out, rom):
    """Caller holds keyboard-flash.lock. Return stock restoration evidence."""
    image,record=assemble(out);record['cpu_checks']=cpu_checks(image)
    record.update(started_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),stage='prepared',hardware_writes=True)
    path=out/'receipt.json'
    def save():
        tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(record,indent=2)+'\n');tmp.replace(path)
    save();device=None
    try:
        program(rom,image,expected,record,save);rom.command(7);rom.close();rom=None
        device=wait_stock()
        response=device.exchange(b'F75Flog!'+bytes(56))
        assert response[:3]==b'F75' and response[3] in (ord('G'),255) and response[4:8]==b'log!'
        assert struct.unpack_from('<I',response,12)[0]==48
        raw=response[16:];(out/'record.bin').write_bytes(raw)
        words=struct.unpack('<12I',raw)
        if words[0]==0x46373546:
            record['diagnostic']=dict(kind='hard_fault',stack_pointer=hex(words[1]),exception_return=hex(words[2]),
                                      control=hex(words[3]),fault_pc=hex(words[10]),stacked_lr=hex(words[9]),xpsr=hex(words[11]))
        elif words[0]==0x43373546:
            record['diagnostic']=dict(kind='checkpoint_reached',checkpoint_address=hex(words[1]))
        else:record['diagnostic']=dict(kind='no_valid_record',magic=hex(words[0]))
        record['stage']='record_captured';save()
    except Exception as error:
        record['error']=str(error);save();raise
    finally:
        if device:device.close()
        if rom:rom.close()
        if record.get('program_verified'):
            app=wait_stock();app.close()
            loader=Rom(0x0c45,0x800a)
            try:
                loader.write(bytes.fromhex('aa42895aff7162cc')+bytes(56));time.sleep(.1)
                restoration=dict(erase_requested=False,security_restore_requested=False);record['restore']=restoration
                program(loader,STOCK.read_bytes(),checksum(image),restoration,save);loader.command(7)
                record['stage']='stock_restored';save()
            finally:loader.close()
    print('Diagnostic record:',json.dumps(record['diagnostic']),flush=True)
    return path,record


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--expected-checksum',required=True,type=lambda s:int(s,16))
    args=parser.parse_args()
    out=ROOT/'analysis/fault-record'/uuid.uuid4().hex;out.mkdir(parents=True)
    fd=os.open(ROOT/'.runtime/keyboard-flash.lock',os.O_RDWR|os.O_NOFOLLOW);fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
    try:
        rom=Rom(0x0c45,0x7140)
        path,result=capture_from_rom(args.expected_checksum,out,rom)
        print('Receipt:',path,flush=True)
    finally:os.close(fd)


if __name__=='__main__':main()
