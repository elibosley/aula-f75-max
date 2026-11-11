#!/usr/bin/env python3
"""Flash the checked wired candidate through the identified SN32F29x ROM.

Uses endpoint-zero feature reports without claiming/detaching a keyboard
interface. No command to lower code security is implemented. USB identities
can remain cached during a ROM jump; ACK validation establishes ROM admission.
"""
import argparse
import array
import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import struct
import time
import uuid

import usb.backend.libusb1
import usb.core
import usb.util
from recovery_image import verify_recovery

ROOT = Path(__file__).resolve().parents[1]
IMAGE = ROOT / 'analysis/UNFLASHED/f75max-wired-test.bin'
STOCK = ROOT / 'analysis/firmware/supplier-f75max-firmware/application.bin'
HARDWARE_REJECTED_IMAGES = {
    '03b4110600203831d35eaad0f0d83e2d53d7dc05cf5f4f8d0d8372d7c78dfc6c',
    'f1d2333605f3565211db8ee1b3684854357754d6319651767b46190b54d87820',
    'db506b84499b529052427afdc0d637fb5e189044e4cc0ea9d002063972182b9c',
}


def checksum(data):
    if len(data) % 2:
        raise ValueError('Image must contain whole 16-bit words')
    return sum(struct.unpack('<' + str(len(data) // 2) + 'H', data)) & 65535

def preserve_settings(image,backup,expected_current):
    """Restore only whitelisted settings regions into an admitted blank image."""
    source_sha=backup['source_image_sha256']
    if len(source_sha)!=64 or any(c not in '0123456789abcdef' for c in source_sha):
        raise ValueError('Invalid settings source identity')
    source=(ROOT/'analysis/candidates'/source_sha/'f75max-wired-test.bin').read_bytes()
    if hashlib.sha256(source).hexdigest()!=source_sha:raise ValueError('Settings source image changed')
    records=backup['records_hex']
    if len(records)!=2:raise ValueError('Exactly two settings records required')
    merged=bytearray(image);current=bytearray(source)
    for address,record in zip([0x3f000,0x3f400],records):
        value=bytes.fromhex(record)
        if len(value)!=160:raise ValueError('Wrong settings record length')
        if image[address:address+1024]!=b'\xff'*1024:raise ValueError('Candidate has no reserved settings page')
        current[address:address+160]=value;merged[address:address+160]=value
    regions=backup.get('custom_regions',[])
    if regions:
        if len(regions)!=2 or [r['address'] for r in regions]!=[0x38000,0x39000]:raise ValueError('Invalid customization region addresses')
        for region in regions:
            address=region['address'];value=bytes.fromhex(region['hex'])
            if len(value)!=4096:raise ValueError('Wrong customization record length')
            if source[address:address+4096]!=b'\xff'*4096 or image[address:address+4096]!=b'\xff'*4096:raise ValueError('Image lacks reserved customization region')
            current[address:address+4096]=value;merged[address:address+4096]=value
    if checksum(current)!=expected_current or backup['source_checksum']!=f'{expected_current:04x}':
        raise ValueError('Settings backup does not match expected current checksum')
    return bytes(merged)


def load_candidate(expected):
    if expected in HARDWARE_REJECTED_IMAGES:
        raise ValueError('Hardware-rejected image: Bluetooth replies alias the Apple Fn input field')
    data = IMAGE.read_bytes()
    actual = hashlib.sha256(data).hexdigest()
    build = json.loads(IMAGE.with_suffix('.json').read_text())
    checks = json.loads((ROOT / 'analysis/keyboard-image-tests.json').read_text())
    system = json.loads((IMAGE.parent / 'system-tests.json').read_text())
    if not actual == expected == build['artifacts'][IMAGE.name]['sha256'] == checks['candidate_sha256']:
        raise ValueError('Candidate does not match the exact build and compiled ARM checks')
    verify_recovery(data, build, checks)
    verify_system_checks(data, IMAGE.with_suffix('.elf').read_bytes(), build, system)
    if len(data) != 262144 or data[-4:] != struct.pack('<I', 0xaaaa5555):
        raise ValueError('Wrong image length or validity flag')
    sp, reset = struct.unpack_from('<II', data)
    if not (0x20000000 < sp <= 0x20008000 and sp % 8 == 0 and reset & 1 and reset < len(data)):
        raise ValueError('Invalid vectors')
    factory = STOCK.read_bytes()
    if hashlib.sha256(factory).hexdigest() != build['stock_source_sha256']:
        raise ValueError('Preserved supplier image changed')
    return data


def verify_system_checks(data, elf, build, system):
    """Offline admission only; a modeled pass does not qualify physical recovery."""
    cases = {(c['wheel_held'], c['magic'], c['reached'])
             for c in system.get('reset_recovery', {}).get('cases', [])}
    expected = {(False, False, 'c_runtime'), (True, False, 'rom_boundary'),
                (False, True, 'rom_boundary'), (True, True, 'rom_boundary')}
    if not (system.get('status') == 'passed'
            and system.get('candidate_sha256') == hashlib.sha256(data).hexdigest()
            and system.get('elf_sha256') == hashlib.sha256(elf).hexdigest()
            and system.get('profile') == build.get('profile')
            and system.get('function_stubs') == []
            and system.get('unmodeled_mmio_accesses') == 0
            and system.get('clock_states', {}).get('valid_handoff_values_reach_main') == list(range(16))
            and system.get('usb', {}).get('configured') is True
            and system.get('factory_loader', {}).get('status') == 'passed'
            and cases == expected):
        raise ValueError('Candidate lacks matching complete ARM system checks and reset-recovery cases')


class Rom:
    def __init__(self, vid=0x0c45, pid=0x800a):
        self.backend = usb.backend.libusb1.get_backend(find_library=lambda _: '/opt/homebrew/lib/libusb-1.0.dylib')
        devices = list(usb.core.find(find_all=True, idVendor=vid, idProduct=pid, backend=self.backend))
        if len(devices) != 1:
            raise RuntimeError('Exactly one requested USB target must be present')
        self.device = devices[0]
        self.handle = self.device._ctx.managed_open()

    def close(self):
        usb.util.dispose_resources(self.device)

    def write(self, data):
        if len(data) != 64:
            raise ValueError('A ROM report must have exactly 64 payload bytes')
        count = self.backend.ctrl_transfer(self.handle, 0x21, 9, 0x0300, 0, array.array('B', data), 1500)
        if count != 64:
            raise RuntimeError(f'Short ROM write: {count}')

    def reply(self, opcode, timeout=15000):
        data = array.array('B', bytes(64))
        count = self.backend.ctrl_transfer(self.handle, 0xa1, 1, 0x0300, 0, data, timeout)
        raw = bytes(data[:count])
        if count != 64 or struct.unpack_from('<II', raw) != (0x55aa00 | opcode, 0xfafafafa):
            raise RuntimeError(f'Invalid ROM ACK for opcode {opcode}: {raw.hex()}')
        return raw

    def command(self, opcode, fields=None):
        if opcode not in {1, 3, 4, 5, 6, 7}:
            raise ValueError('Unsupported command')
        data = bytearray(64)
        struct.pack_into('<I', data, 0, 0x55aa00 | opcode)
        for offset, fmt, value in fields or []:
            struct.pack_into(fmt, data, offset, value)
        self.write(bytes(data))
        if opcode == 7:
            return None
        time.sleep(.02)
        return self.reply(opcode)

    def identify(self):
        data = self.command(1)
        identity = dict(family=data[8], chip=data[9], revision=data[11],
                        code_option=struct.unpack_from('<H', data, 12)[0],
                        security=struct.unpack_from('<H', data, 14)[0])
        if (identity['family'], identity['chip']) != (32, 5):
            raise RuntimeError(f'Expected SN32F29x, received {identity}')
        if identity['security'] not in {0xffff, 0x5a5a}:
            raise RuntimeError('Unqualified code security level')
        if identity['code_option'] & 5 != 5:
            raise RuntimeError('ROM and boot-pin code options must remain enabled')
        return identity

    def sum(self):
        return struct.unpack_from('<H', self.command(6), 8)[0]


def program(rom, image, expected_current, record, save):
    identity = rom.identify()
    current = rom.sum()
    record.update(identity_before=identity, checksum_before=f'{current:04x}')
    save()
    if current != expected_current:
        raise RuntimeError('Installed checksum changed since the hardware preflight; no erase admitted')
    record['erase_requested'] = True; record['stage'] = 'erase_started'; save()
    erased = rom.command(4, [(4, '<H', 0), (8, '<H', 256)])
    if struct.unpack_from('<H', erased, 8)[0] != 0 or rom.sum() != 0:
        raise RuntimeError('Erase checksum is not the qualified blank value')
    record['erase_verified'] = True; record['stage'] = 'erase_verified'; save()
    print('Erase verified.', flush=True)
    rom.command(5, [(4, '<I', 0), (8, '<I', len(image) // 64)])
    record['programming_requested'] = True; record['stage'] = 'programming'; save()
    deadline = time.monotonic() + 90
    for offset in range(0, len(image), 64):
        if time.monotonic() > deadline:
            raise TimeoutError('Programming deadline exceeded; leave the device in ROM')
        rom.write(image[offset:offset + 64])
        if (offset + 64) % 32768 == 0:
            record['bytes_written'] = offset + 64; save()
            print(f'Written {offset + 64}/{len(image)} bytes.', flush=True)
    complete = rom.reply(5)
    expected = checksum(image)
    if struct.unpack_from('<I', complete, 60)[0] != struct.unpack_from('<I', image, len(image) - 4)[0]:
        raise RuntimeError('ROM last-word verification failed')
    if struct.unpack_from('<H', complete, 8)[0] != expected or rom.sum() != expected:
        raise RuntimeError('Programmed checksum mismatch; leave the device in ROM')
    after = rom.identify()
    # Some ROM erase implementations change CS implicitly. Restore the original
    # protection only after verifying the image. Never lower protection here.
    if after['code_option'] != identity['code_option']:
        raise RuntimeError('Code options changed unexpectedly; leave the device in ROM')
    if after['security'] != identity['security']:
        if after['security'] != 0xffff or identity['security'] != 0x5a5a:
            raise RuntimeError('Unexpected protection transition')
        record['security_restore_requested'] = True; save()
        rom.command(3, [(4, '<H', identity['code_option']), (6, '<H', identity['security'])])
        after = rom.identify()
        if after['security'] != identity['security'] or rom.sum() != expected:
            raise RuntimeError('Protection restoration did not verify')
    record.update(program_verified=True, checksum_after=f'{expected:04x}', identity_after=after, stage='program_verified')
    save()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--program', action='store_true', required=True)
    parser.add_argument('--sha256', required=True)
    parser.add_argument('--settings-backup',type=Path,help='Explicit fixed-record backup captured before entering ROM')
    parser.add_argument('--expected-current-checksum', type=lambda s: int(s, 16), required=True)
    parser.add_argument('--pid', type=lambda s: int(s, 16), choices=[0x800a,0x7140], default=0x800a,
                        help='7140 selects an already-present factory ROM; 800a requests entry from stock')
    args = parser.parse_args()
    image = load_candidate(args.sha256)
    if args.settings_backup:
        image=preserve_settings(image,json.loads(args.settings_backup.read_text()),args.expected_current_checksum)
    root = ROOT / '.runtime'; root.mkdir(mode=0o700, exist_ok=True)
    lock = os.open(root / 'keyboard-flash.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    attempt = uuid.uuid4().hex
    receipt = ROOT / 'analysis' / f'flash-{attempt}.json'
    record = dict(attempt=attempt, pid=os.getpid(), started_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                  image_sha256=args.sha256, image_bytes=len(image), erase_requested=False, programming_requested=False,
                  erase_verified=False, program_verified=False, return_requested=False, security_restore_requested=False,
                  security_downgrade_requested=False, stage='prepared')
    record['program_payload_sha256']=hashlib.sha256(image).hexdigest()
    record['settings_backup']=str(args.settings_backup) if args.settings_backup else None

    def save():
        temporary = receipt.with_suffix('.tmp')
        temporary.write_text(json.dumps(record, indent=2) + '\n'); temporary.replace(receipt)

    save(); print('Receipt: ' + str(receipt), flush=True)
    rom = None
    try:
        rom = Rom(0x0c45,args.pid)
        if args.pid == 0x800a:
            record['stage'] = 'boot_entry_requested'; save()
            rom.write(bytes.fromhex('aa42895aff7162cc') + bytes(56))
            time.sleep(.1)
        program(rom, image, args.expected_current_checksum, record, save)
        record['return_requested'] = True; save()
        rom.command(7)
        record['stage'] = 'programmed_return_requested'; save()
        print('Programming and checksum verified. Return to application requested.', flush=True)
    except Exception as exc:
        record['error'] = str(exc)
        record['stage'] = 'failed_leave_in_rom' if record['erase_requested'] else 'failed_before_erase'
        if rom and not record['erase_requested']:
            try: rom.command(7); record['return_requested'] = True
            except Exception as back: record['return_error'] = str(back)
        save(); raise
    finally:
        if rom: rom.close()
        os.close(lock)


if __name__ == '__main__':
    main()
