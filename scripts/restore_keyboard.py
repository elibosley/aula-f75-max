#!/usr/bin/env python3
"""Restore the pinned supplier image to an already-present F75 ROM bootloader."""
import datetime
import argparse
import fcntl
import hashlib
import json
import os
import uuid

from flash_keyboard import ROOT, STOCK, Rom, checksum, program

STOCK_SHA = 'a7d458754f3cc3aed7c8956f854148e081bc63f524da230a8ea8d3b3b3a4b5e9'
FAILED_IMAGE_CHECKSUM = 0x2970


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--expected-current-checksum', type=lambda s: int(s, 16), default=FAILED_IMAGE_CHECKSUM)
    parser.add_argument('--pid', type=lambda s: int(s, 16), choices=[0x7140, 0x800a], default=0x7140)
    args = parser.parse_args()
    image = STOCK.read_bytes()
    if hashlib.sha256(image).hexdigest() != STOCK_SHA or len(image) != 262144 or checksum(image) != 0xb9d0:
        raise SystemExit('Supplier image hash, length or checksum changed; no restore admitted')
    lock = os.open(ROOT / '.runtime/keyboard-flash.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    attempt = uuid.uuid4().hex
    path = ROOT / 'analysis' / f'restore-{attempt}.json'
    record = dict(attempt=attempt, pid=os.getpid(), operation='restore_pinned_supplier_image',
                  started_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                  image_sha256=STOCK_SHA, image_bytes=len(image), device_readback=False,
                  erase_requested=False, erase_verified=False, programming_requested=False,
                  program_verified=False, return_requested=False, security_restore_requested=False,
                  security_downgrade_requested=False, stage='prepared')

    def save():
        temporary = path.with_suffix('.tmp')
        temporary.write_text(json.dumps(record, indent=2) + '\n'); temporary.replace(path)

    rom = None
    save(); print('Restore receipt: ' + str(path), flush=True)
    try:
        rom = Rom(0x0c45, args.pid)
        program(rom, image, args.expected_current_checksum, record, save)
        record['return_requested'] = True; save()
        rom.command(7)
        record['stage'] = 'stock_programmed_return_requested'; save()
        print('Stock image checksum verified; return requested.', flush=True)
    except Exception as exc:
        record['error'] = str(exc)
        record['stage'] = 'failed_leave_in_rom' if record['erase_requested'] else 'failed_before_erase'
        save(); raise
    finally:
        if rom: rom.close()
        os.close(lock)


if __name__ == '__main__':
    main()
