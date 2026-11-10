#!/usr/bin/env python3
"""Exercise the computer status command on the linked ARM USB and panel model."""
import argparse
import ctypes
import hashlib
import json
import struct
from pathlib import Path

from display_types import View
from host_display import payload
from serve_emulator import Emulator
from system_emulator import HOST


def run(image):
    emulator = Emulator(image)
    machine = emulator.machine
    try:
        def request(command, data=bytes(24)):
            emulator.reports.clear()
            machine.endpoint_out(3, command + b'dspl' + data)
            emulator.advance(160)
            replies = [bytes.fromhex(report['data']) for report in emulator.reports if report['endpoint'] == 2]
            assert len(replies) == 1 and replies[0][4:8] == b'dspl', replies
            return replies[0]

        def footer():
            frame = View.from_buffer_copy(machine.read(machine.symbols['frame'], ctypes.sizeof(View)))
            return bytes(frame.footer)

        emulator.advance(2500)
        health = request(b'F75?')
        assert health[24] & 16
        baseline = emulator.frame.crop((0, 116, 128, 128)).tobytes()
        reply = request(b'F75y', payload('set', 'Build passed', 2))
        assert reply[:4] == b'F75a' and reply[8:12] == bytes((1, 0, 1, 1)), reply
        assert footer() == b'Build passed', footer()
        assert emulator.frame.crop((0, 116, 128, 128)).tobytes() != baseline
        assert not any(report['endpoint'] == 1 for report in emulator.reports)

        malformed = bytearray(payload('set', 'A', 2))
        malformed[4] = 27
        assert request(b'F75y', malformed)[9] == 1
        assert footer() == b'Build passed'
        emulator.action('press')
        assert footer() != b'Build passed'
        emulator.action('back')
        emulator.advance(2100)
        assert request(b'F75y', payload('info'))[11] == 0
        assert footer() != b'Build passed'
        request(b'F75y', payload('set', 'Clear this', 20))
        assert request(b'F75y', payload('clear'))[11] == 0
        assert footer() != b'Clear this'

        request(b'F75y', payload('set', 'USB message', 20))
        machine.write32(HOST + 0x200, (1 << 10) | (1 << 2) | (1 << 3))
        machine.write32(HOST + 0x204, 0)
        emulator.advance(150)
        assert request(b'F75y', payload('set', 'Wrong route', 20))[9:12] == bytes((2, 0, 0))
        machine.write32(HOST + 0x204, 1 << 2)
        emulator.advance(200)
        assert request(b'F75y', payload('info'))[9:12] == bytes((0, 1, 0))

        now = struct.unpack_from('<I', request(b'F75?'), 8)[0]
        machine.write32(machine.symbols['state'] + 116, (now - 46000) & 0xffffffff)
        emulator.advance(50)
        frames = machine.read32(machine.symbols['complete_frames'])
        assert request(b'F75y', payload('set', 'Keep sleeping', 20))[11] == 1
        assert machine.read32(machine.symbols['complete_frames']) == frames
        assert not machine.read32(0x40044000) & (1 << 16)
        assert machine.read32(HOST + 0x58) == machine.read32(HOST + 0x5c) == 0
        return {'status': 'passed', 'candidate_sha256': hashlib.sha256(image.read_bytes()).hexdigest(),
                'usb_to_panel': True, 'expiry_and_clear': True, 'route_guard': True,
                'invalid_text_rejected': True, 'stays_asleep': True, 'flash_writes': False}
    finally:
        machine.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('image', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = run(args.image)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))
