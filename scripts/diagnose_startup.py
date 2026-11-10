#!/usr/bin/env python3
"""Run one pinned startup checkpoint and restore stock after observed ROM return.

A successful checkpoint requires a timeout while its CPU-only delay runs,
followed by a validated ROM ACK. Immediate ACK alone is not execution proof.
The failed original image stays archived unchanged. No security lowering.
"""
import argparse
import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import shutil
import time
import uuid
from flash_keyboard import ROOT, STOCK, Rom, checksum, program, verify_system_checks
from recovery_image import verify_recovery

BASE = ROOT / 'analysis/UNFLASHED/f75max-wired-test.bin'
STOCK_SHA = 'a7d458754f3cc3aed7c8956f854148e081bc63f524da230a8ea8d3b3b3a4b5e9'
ALLOWED = {'_crt0_entry', '__early_init', 'early_hardware_init_post', '__late_init',
           'SystemCoreClockUpdate', 'FlashClockUpdate', '__init_ram_areas',
           'main', 'hal_lld_init', 'SystemInit', 'sn32_clock_init', 'chSysInit', 'protocol_setup',
           'protocol_pre_init', 'keyboard_pre_init_user', 'keyboard_post_init_user', 'usb_lld_start'}

def connect():
    for pid in (0x7140, 0x800a):
        try:
            return Rom(0x0c45, pid)
        except Exception:
            pass
    raise RuntimeError('No target USB identity present')

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('checkpoint', choices=sorted(ALLOWED))
    ap.add_argument('--run', action='store_true')
    args = ap.parse_args()
    image = bytearray(BASE.read_bytes()); stock = STOCK.read_bytes()
    base_sha = hashlib.sha256(image).hexdigest()
    build = json.loads(BASE.with_suffix('.json').read_text())
    checks = json.loads((ROOT / 'analysis/keyboard-image-tests.json').read_text())
    if base_sha != build['artifacts'][BASE.name]['sha256'] or base_sha != checks['candidate_sha256']:
        raise ValueError('Diagnostic base does not match the checked build')
    guard = verify_recovery(image, build, checks)
    system = json.loads((BASE.parent / 'system-tests.json').read_text())
    verify_system_checks(image, BASE.with_suffix('.elf').read_bytes(), build, system)
    assert hashlib.sha256(stock).hexdigest() == STOCK_SHA
    tc = ROOT / 'builddeps/arm-toolchain/bin'
    attempt = uuid.uuid4().hex
    out = ROOT / 'analysis/diagnostics' / attempt
    out.mkdir(parents=True)
    symbol_listing = subprocess.check_output([str(tc / 'arm-none-eabi-nm'), '-n', str(BASE.with_suffix('.elf'))], text=True)
    checkpoint_address = next(int(line.split()[0],16) for line in symbol_listing.splitlines()
                              if len(line.split()) == 3 and line.split()[2] == args.checkpoint)
    subprocess.run([str(tc / 'arm-none-eabi-gcc'), '-mcpu=cortex-m0', '-mthumb', '-nostdlib',
                    '-Wl,-Ttext=0x3e000', '-Wl,-e,checkpoint',
                    '-DF75_ROM_RETURN=' + str(guard['rom_entry']),
                    '-DF75_CHECKPOINT_ADDRESS=' + str(checkpoint_address),
                    str(ROOT / 'firmware/diagnostics/checkpoint.S'), '-o', str(out / 'checkpoint.elf')], check=True)
    subprocess.run([str(tc / 'arm-none-eabi-objcopy'), '-O', 'binary', str(out / 'checkpoint.elf'), str(out / 'checkpoint.bin')], check=True)
    symbols = {}
    elf = BASE.with_suffix('.elf')
    for line in subprocess.check_output([str(tc / 'arm-none-eabi-nm'), '-n', str(elf)], text=True).splitlines():
        fields = line.split()
        if len(fields) == 3: symbols[fields[2]] = int(fields[0], 16)
    address = symbols[args.checkpoint]
    # A literal load through r0 is valid at any halfword-aligned entry.
    literal = (address + 7) & ~3
    jump = struct.pack('<HH', 0x4800 | ((literal - ((address + 4) & ~3)) // 4), 0x4700)
    jump += bytes(literal - address - 4) + struct.pack('<I', 0x3e001)
    assert address < 0x10000 and len(jump) <= 10
    if address < guard['end'] and address + len(jump) > guard['start']:
        raise ValueError('Diagnostic would overwrite the wheel recovery region')
    stub = (out / 'checkpoint.bin').read_bytes()
    assert len(stub) < 128 and all(v == 0 for v in image[0x3e000:0x3e000+len(stub)])
    image[address:address+len(jump)] = jump
    image[0x3e000:0x3e000+len(stub)] = stub
    verify_recovery(image, build, checks)
    (out / 'image.bin').write_bytes(image)
    record = dict(attempt=attempt, checkpoint=args.checkpoint, checkpoint_address=hex(address),
                  started_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                  image_sha256=hashlib.sha256(image).hexdigest(), image_checksum=f'{checksum(image):04x}',
                  base_sha256=base_sha, stock_sha256=STOCK_SHA, hardware_writes=False,
                  reset_recovery=guard, wheel_recovery_bytes_unchanged=True,
                  stage='prepared', erase_requested=False, security_restore_requested=False)
    path = out / 'receipt.json'
    def save():
        tmp = path.with_suffix('.tmp'); tmp.write_text(json.dumps(record, indent=2)+'\n'); tmp.replace(path)
    save(); print('Diagnostic receipt:', path, flush=True)
    (out / 'base-build.json').write_text(json.dumps(build, indent=2)+'\n')
    (out / 'base-tests.json').write_text(json.dumps(checks, indent=2)+'\n')
    shutil.copytree(ROOT / 'builddeps/qmk/keyboards/aula/f75max_test', out / 'board-source')
    from system_emulator import System
    with System(out / 'image.bin', symbols_file=BASE.with_suffix('.elf'), factory_rom=True) as model:
        model.poll_checkpoint = 0x1fff03bc
        model.pump()
        marker = struct.unpack('<II', model.read(0x20007e00, 8))
        assert marker == (0x43373546, address), ('Patched diagnostic did not reach its checkpoint in emulation', marker)
    record['patched_image_execution'] = 'reset_to_checkpoint_marker_to_actual_factory_rom_passed'; save()
    if not args.run: return
    lock = os.open(ROOT / '.runtime/keyboard-flash.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    rom = None
    try:
        rom = connect()
        try: identity = rom.identify()
        except Exception:
            rom.write(bytes.fromhex('aa42895aff7162cc') + bytes(56)); time.sleep(.1)
            identity = rom.identify()
        # Only replace the restored stock image. Never overwrite an unknown trial.
        record['hardware_writes'] = True
        program(rom, bytes(image), 0xb9d0, record, save)
        record['stage'] = 'checkpoint_requested'; save()
        rom.command(7); rom.close(); rom = None
        # A cold button request can enter ROM before the selected checkpoint.
        # An explicit second return consumes the guard's one-time exit marker.
        time.sleep(3)
        rom = connect()
        assert rom.sum() == checksum(image)
        rom.command(7); rom.close(); rom = None
        time.sleep(3)
        rom = connect()
        assert rom.sum() == checksum(image)
        from read_fault_record import capture_from_rom
        capture_dir = out / 'captured-record'; capture_dir.mkdir()
        capture_path, capture = capture_from_rom(checksum(image), capture_dir, rom)
        rom = None
        record['capture_receipt'] = str(capture_path.relative_to(ROOT))
        record['diagnostic'] = capture['diagnostic']
        reached = capture['diagnostic']
        record['checkpoint_execution'] = ('sram_marker_verified' if reached.get('kind') == 'checkpoint_reached'
            and int(reached['checkpoint_address'],16) == address else 'checkpoint_not_reached')
        record['stage'] = 'stock_restored_return_requested'; save()
        print('Checkpoint observation:', record['checkpoint_execution'], flush=True)
    except Exception as exc:
        record['error'] = str(exc); save(); raise
    finally:
        if rom: rom.close()
        os.close(lock)

if __name__ == '__main__': main()
