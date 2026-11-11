#!/usr/bin/env python3
"""Exercise the computer status command on the linked ARM USB and panel model."""
import argparse
import ctypes
import hashlib
import json
import struct
import zlib
from pathlib import Path

from display_types import View
from host_display import payload
from serve_emulator import Emulator
from system_emulator import HOST, System


def bluetooth_symbols(operation, text=b'', seconds=0, *, corrupt=False):
    data = bytes((operation, seconds, len(text))) + text
    checksum = zlib.crc32(data) ^ corrupt
    previous = 7
    yield previous
    for byte in data + checksum.to_bytes(4, 'little'):
        for shift in (6, 4, 2, 0):
            digit = (byte >> shift) & 3
            previous = digit + 1 if previous == 7 else (previous + digit) % 6 + 1
            yield previous


def bluetooth_without_usb(image):
    with System(image) as machine:
        machine.until('keyboard_post_init_user')
        machine.write32(HOST + 0x204, 0)
        machine.until('housekeeping_task_user')

        def advance(milliseconds):
            for elapsed in range(0, milliseconds, 10):
                machine.write32(HOST + 0x30, 0)
                machine.advance(min(10, milliseconds - elapsed))
                machine.pump()

        def radio_packet(*packet):
            for byte in packet:
                machine.write32(HOST + 0x44, byte)
            advance(2)

        advance(100)
        radio_packet(0x5b, 0x32, 0x8d)
        assert machine.read(machine.symbols['active_slot'], 1) == b'\1'
        assert machine.read(machine.symbols['connected'], 1) == b'\1'
        advance(2400)
        frames = machine.read32(machine.symbols['complete_frames'])
        for symbol in bluetooth_symbols(1, b'Wireless', 10):
            value = symbol << 5
            radio_packet(0x5a, value, (0x5a + value) & 0xff)
        advance(160)
        view = View.from_buffer_copy(machine.read(machine.symbols['frame'], ctypes.sizeof(View)))
        assert bytes(view.footer) == b'Wireless'
        assert view.pet_info and view.info_progress == 255
        assert machine.read32(machine.symbols['complete_frames']) > frames
        assert not machine.endpoint_in(1)


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
        baseline = emulator.frame.crop((0, 72, 128, 128)).tobytes()
        reply = request(b'F75y', payload('set', 'Build passed', 2))
        assert reply[:4] == b'F75a' and reply[8:12] == bytes((1, 0, 1, 1)), reply
        assert footer() == b'Build passed', footer()
        assert emulator.frame.crop((0, 72, 128, 128)).tobytes() != baseline
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

        def radio_packet(*packet):
            for byte in packet:
                machine.write32(HOST + 0x44, byte)
            emulator.advance(2)

        def bluetooth_route():
            machine.write32(HOST + 0x200, (1 << 10) | (1 << 2) | (1 << 3))
            machine.write32(HOST + 0x204, 0)
            emulator.advance(35)
            radio_packet(0x61, 0x0d, 0x0a)
            radio_packet(0x5b, 0x32, 0x8d)
            assert machine.read(machine.symbols['active_slot'], 1) == b'\1'
            assert machine.read(machine.symbols['connected'], 1) == b'\1'

        def symbols(sequence):
            for symbol in sequence:
                value = symbol << 5
                radio_packet(0x5a, value, (0x5a + value) & 0xff)

        machine.write32(machine.symbols['state'] + 116, struct.unpack_from('<I', request(b'F75?'), 8)[0])
        bluetooth_route()
        emulator.advance(2400)
        message = b'Bluetooth status ok?'
        frame = tuple(bluetooth_symbols(1, message, 4))
        symbols(bluetooth_symbols(1, message, 4, corrupt=True))
        emulator.advance(160)
        assert footer() != message
        symbols(frame[:12])
        radio_packet(0x5b, 0x33, 0x8e)
        radio_packet(0x5b, 0x32, 0x8d)
        symbols(frame[12:])
        emulator.advance(160)
        assert footer() != message
        symbols(frame[:12])
        emulator.advance(1550)
        symbols(frame[12:])
        emulator.advance(160)
        assert footer() != message
        bluetooth_baseline = emulator.frame.crop((0, 72, 128, 128)).tobytes()
        symbols(symbol for value in frame for symbol in (value, value))
        emulator.advance(160)
        assert footer() == message, footer()
        assert emulator.frame.crop((0, 72, 128, 128)).tobytes() != bluetooth_baseline
        assert request(b'F75y', payload('clear'))[11] == 0
        assert footer() == message
        symbols(bluetooth_symbols(2))
        emulator.advance(160)
        assert footer() != message
        symbols(bluetooth_symbols(1, message, 1))
        emulator.advance(160)
        assert footer() == message
        emulator.advance(1000)
        assert footer() != message
        symbols(frame)
        emulator.advance(160)
        assert footer() == message
        def reply_frame(challenge):
            values=(0x80,0x40,0x20,0x10,8,4,2,1,0x55,0xaa,0xfe,0xff,0x7f,0x81,0x5a,0xa5)
            report = bytes((0xa1,0,values[challenge])) + bytes(6)
            return report + bytes((sum(report) & 0xff,))

        def radio_trace():
            return machine.read(0x61000000, machine.read32(HOST + 0x40))

        trace_before = len(radio_trace())
        symbols(bluetooth_symbols(3, seconds=5))
        emulator.advance(20)
        assert reply_frame(5) in radio_trace()[trace_before:]
        radio_packet(0x61, 0x0d, 0x0a)
        machine.write(machine.symbols['key_owners'] + 4, b'\1')
        trace_before = len(radio_trace())
        symbols(bluetooth_symbols(3, seconds=6))
        emulator.advance(20)
        assert reply_frame(6) not in radio_trace()[trace_before:]
        machine.write(machine.symbols['key_owners'] + 4, b'\0')
        assert footer() == message
        machine.write32(HOST + 0x204, 1 << 2)
        emulator.advance(200)
        assert footer() != message
        return {'status': 'passed', 'candidate_sha256': hashlib.sha256(image.read_bytes()).hexdigest(),
                'usb_to_panel': True, 'expiry_and_clear': True, 'route_guard': True,
                'invalid_text_rejected': True, 'stays_asleep': True, 'flash_writes': False,
                'modeled_bluetooth_uart_to_panel': True, 'corrupt_bluetooth_frames_rejected': True,
                'bluetooth_frame_reset_on_disconnect_and_timeout': True,
                'reply_probe_uart_frame_and_held_key_guard': True}
    finally:
        machine.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('image', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = run(args.image)
    bluetooth_without_usb(args.image)
    result['bluetooth_status_without_usb_enumeration'] = True
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))
