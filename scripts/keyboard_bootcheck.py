#!/usr/bin/env python3
"""One bootloader round trip. Only entry, identify, checksum and return commands.

No security, erase, program, or flash-read command is implemented here.
"""
import datetime
import argparse
import array
import json
from pathlib import Path
import struct
import time

import hid
import usb.backend.libusb1
import usb.core
import usb.util

ROOT = Path(__file__).resolve().parents[1]


def devices(pid):
    return hid.enumerate(0x0c45, pid)


def wait_for(pid, seconds):
    deadline = time.monotonic() + seconds
    while True:
        found = devices(pid)
        if found:
            return found
        if time.monotonic() >= deadline:
            return []
        time.sleep(.1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--interface', type=int, choices=[0, 3], default=3)
    parser.add_argument('--transport', choices=['hid', 'libusb'], default='hid')
    args = parser.parse_args()
    receipt = ROOT / f'analysis/keyboard-bootcheck-{args.transport}-iface{args.interface}.json'
    if receipt.exists():
        raise SystemExit('This interface attempt already has a receipt; inspect it instead of repeating boot entry')
    result = dict(observed_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                  bootloader_entry_requested=False, erase_requested=False,
                  security_change_requested=False, programming_requested=False,
                  return_requested=False, original_application_returned=False, commands=[])

    def save():
        temporary = receipt.with_suffix('.tmp')
        temporary.write_text(json.dumps(result, indent=2) + '\n')
        temporary.replace(receipt)

    def send(device, payload, label):
        result['commands'].append(dict(command=label, payload_prefix=payload[:8].hex(), state='started'))
        save()
        count = device.send_feature_report(b'\0' + payload.ljust(64, b'\0'))
        result['commands'][-1].update(state='returned', count=count)
        save()
        return count

    def query(device, opcode):
        assert opcode in {1, 6}
        payload = struct.pack('<I', 0x55aa00 | opcode)
        send(device, payload, 'identify' if opcode == 1 else 'checksum')
        time.sleep(.05)
        raw = bytes(device.get_feature_report(0, 65))
        data = raw[1:] if len(raw) == 65 and raw[0] == 0 else raw
        result['commands'][-1]['response_hex'] = raw.hex()
        save()
        if len(data) != 64 or struct.unpack_from('<II', data) != (0x55aa00 | opcode, 0xfafafafa):
            raise RuntimeError('Bootloader response lacks the expected command and ACK; an echo is not identification')
        return data

    existing = devices(0x7140)
    if existing:
        raise SystemExit('A bootloader is already present; inspect it before starting another entry attempt')
    page = 0xff13 if args.interface == 3 else 1
    app = [d for d in devices(0x800a) if d['interface_number'] == args.interface and d['usage_page'] == page]
    if len(app) != 1:
        raise SystemExit('Exactly one F75 Max command interface must be present')
    error = None
    result['application_interface'] = args.interface
    result['application_transport'] = args.transport
    try:
        if args.transport == 'hid':
            with hid.Device(path=app[0]['path']) as device:
                result['bootloader_entry_requested'] = True
                send(device, bytes.fromhex('aa42895aff7162cc'), 'hfd_boot_entry')
        else:
            backend = usb.backend.libusb1.get_backend(find_library=lambda _: '/opt/homebrew/lib/libusb-1.0.dylib')
            targets = list(usb.core.find(find_all=True, idVendor=0x0c45, idProduct=0x800a, backend=backend))
            if len(targets) != 1:
                raise RuntimeError('Exactly one matching USB device is required')
            target = targets[0]
            try:
                handle = target._ctx.managed_open()
                # Endpoint-zero class request. No interface claim, driver detach,
                # input reads, security transition, erase, or programming.
                payload = array.array('B', bytes.fromhex('aa42895aff7162cc') + bytes(56))
                result['bootloader_entry_requested'] = True
                result['commands'].append(dict(command='hfd_boot_entry', interface=args.interface,
                                               transport='libusb_control', payload_prefix=bytes(payload[:8]).hex(), state='started'))
                save()
                count = backend.ctrl_transfer(handle, 0x21, 9, 0x0300, args.interface, payload, 1000)
                result['commands'][-1].update(state='returned', count=count)
                save()
            finally:
                usb.util.dispose_resources(target)
        boot = wait_for(0x7140, 5)
        if len(boot) != 1:
            raise RuntimeError(f'Expected one ROM bootloader interface, observed {len(boot)}')
        result['bootloader_observed'] = True
        with hid.Device(path=boot[0]['path']) as device:
            version = query(device, 1)
            result['identity'] = dict(family_version=version[8], chip_version=version[9],
                                      chip_revision=version[11], security_raw=f'{struct.unpack_from("<H", version, 14)[0]:04x}')
            checksum = query(device, 6)
            result['checksum'] = f'{struct.unpack_from("<H", checksum, 8)[0]:04x}'
    except Exception as exc:
        error = str(exc)
        result['error'] = error
    finally:
        boot = devices(0x7140)
        if len(boot) == 1:
            try:
                with hid.Device(path=boot[0]['path']) as device:
                    result['return_requested'] = True
                    send(device, struct.pack('<I', 0x55aa07), 'return_user_mode')
            except Exception as exc:
                result['return_error'] = str(exc)
        result['original_application_returned'] = bool(wait_for(0x800a, 5))
        result['status'] = 'bootloader_round_trip_passed' if not error and result['original_application_returned'] else 'round_trip_not_verified'
        save()
        print(json.dumps(result, indent=2))
    if result['status'] != 'bootloader_round_trip_passed':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
