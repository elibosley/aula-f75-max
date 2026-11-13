#!/usr/bin/env python3
"""Check Mac modifier ownership in actual ARM USB and modeled radio reports.

This never accesses a physical keyboard or emulates a Bluetooth controller.
"""
import argparse
import hashlib
import json
import struct
from pathlib import Path

from system_emulator import System, HOST
from test_system_emulator import enumerate_usb


def run(image):
    checks = []
    with System(image) as m:
        enumerate_usb(m)
        radio = False
        usb = bytes(8)
        rows = [0] * 15
        keymap = struct.unpack('<90H', m.read(m.symbols['keymaps'], 180))
        fn = 71

        def step(ms=25):
            nonlocal usb
            for elapsed in range(0, ms, 2):
                m.write32(HOST + 0x30, 0)
                m.advance(min(2, ms - elapsed)); m.pump()
                if radio and m.read(m.symbols['waiting'], 1) == b'\1':
                    for byte in b'\x61\r\n': m.write32(HOST + 0x44, byte)
                    m.advance(1); m.pump()
                for _ in range(20):
                    packet = m.endpoint_in(1)
                    if packet is None: break
                    usb = packet

        def key(index, down):
            row, col = divmod(index, 6)
            rows[row] = (rows[row] | (1 << col)) if down else (rows[row] & ~(1 << col))
            m.write32(HOST + 0x100 + row * 4, rows[row]); step()

        def usage(code, down): key(keymap.index(code), down)

        def report():
            if not radio: return usb
            trace = m.read(0x61000000, m.read32(HOST + 0x40))
            packets = [trace[i+1:i+9] for i in range(len(trace)-9)
                       if trace[i] == 0xa1 and trace[i+9] == (sum(trace[i:i+9]) & 255)]
            assert packets, 'No UART keyboard report'
            return packets[-1]

        def expect(mod=0, code=0):
            expected = bytes([mod, 0, code, 0, 0, 0, 0, 0])
            assert report() == expected, (radio, report().hex(), expected.hex())

        def cases():
            slot = 1 if radio else 0
            for os in range(3):
                m.write(m.symbols['state'] + slot, bytes([os]))
                usage(0x39, True); expect(8 if os == 0 else 1)
                usage(0x39, False); expect()
                usage(0xe0, True); expect(1 if os == 0 else 0, 0 if os == 0 else 0x39)
                usage(0xe0, False); expect()
                key(fn, True); usage(0x39, True)
                expect(0 if os == 0 else 1, 0x39 if os == 0 else 0)
                # Releasing Fn first must release the captured Caps action, not Command.
                key(fn, False); expect(0 if os == 0 else 1, 0x39 if os == 0 else 0)
                usage(0x39, False); expect()
            m.write(m.symbols['state'] + slot, b'\0')
            usage(0xe0, True); usage(6, True); expect(1, 6)
            usage(0xe0, False); expect(0, 6); usage(6, False); expect()
            # Caps first captures Command even if Fn changes while it is held.
            usage(0x39, True); key(fn, True); expect(8)
            usage(0x39, False); expect(); key(fn, False); expect()
            key(fn, True); usage(0x39, True); expect(0, 0x39)
            usage(0x39, False); expect(); key(fn, False); expect()
            # A logical custom Fn binding has priority over the default chord.
            binding = m.symbols['f75_custom_config'] + 2 * (90 + keymap.index(0x39))
            m.write(binding, struct.pack('<H', 0xe2))
            key(fn, True); usage(0x39, True); expect(4)
            key(fn, False); usage(0x39, False); expect()
            m.write(binding, bytes(2))
            checks.append(dict(transport='uart' if radio else 'usb', os_profiles=3,
                               ctrl_c=True, both_release_orders=True,
                               press_action_captured=True, custom_binding_wins=True))

        step(400); cases()
        radio = True
        m.write32(HOST + 0x200, (1 << 10) | (1 << 2) | (1 << 3))
        m.write32(HOST + 0x204, 0); step(100)
        for byte in bytes.fromhex('5b328d'): m.write32(HOST + 0x44, byte)
        step(100)
        assert m.read(m.symbols['active_slot'], 1) == b'\1'
        assert m.read(m.symbols['connected'], 1) == b'\1'
        cases()
        assert m.read(m.symbols['navigation'], 1) == b'\0'
    return dict(status='passed', candidate_sha256=hashlib.sha256(image.read_bytes()).hexdigest(),
                hardware_writes=False, physical_hardware_tested=False, real_arm=True, checks=checks)


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('image', type=Path)
    p.add_argument('--output', type=Path, required=True); a = p.parse_args()
    result = run(a.image); a.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))
