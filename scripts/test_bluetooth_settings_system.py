#!/usr/bin/env python3
"""Exercise the linked ARM Bluetooth settings adapter with modeled UART events.

This tests main-controller code, not a Bluetooth radio or physical RF link.
"""
import argparse
import ctypes
import hashlib
import json
import struct
import zlib
from pathlib import Path

from keyboard_customize import BUNDLE_BYTES, validate
from keyboard_bluetooth import snapshot_crc
from system_emulator import HOST, System
from test_host_display_system import bluetooth_symbols

class ReplyState(ctypes.Structure):
    _fields_ = [('response', ctypes.c_uint8 * 271), ('length', ctypes.c_uint16),
                ('index', ctypes.c_uint16), ('touched', ctypes.c_uint32),
                ('started', ctypes.c_uint32), ('owns', ctypes.c_bool), ('replying', ctypes.c_bool)]


def run(image, consumer_only=False, clock_only=False):
    with System(image) as m:
        m.until('housekeeping_task_user')

        def step(ms=2):
            for elapsed in range(0, ms, 2):
                m.write32(HOST + 0x30, 0)
                m.advance(min(2, ms - elapsed)); m.pump()
                if m.read(m.symbols['waiting'], 1) == b'\1':
                    for byte in b'\x61\x0d\x0a':
                        m.write32(HOST + 0x44, byte)
                    m.advance(1); m.pump()

        def inject(data):
            for byte in data:
                m.write32(HOST + 0x44, byte)
            step()

        def trace():
            return m.read(0x61000000, m.read32(HOST + 0x40))

        def symbols(data):
            for symbol in bluetooth_symbols(4, data, 1):
                value = symbol << 5
                inject(bytes((0x5a, value, (0x5a + value) & 255)))

        step(100)
        m.write32(HOST + 0x200, (1 << 10) | (1 << 2) | (1 << 3))
        m.write32(HOST + 0x204, 0)
        step(100); inject(b'\x5b\x32\x8d'); step(100)
        assert m.read(m.symbols['active_slot'], 1) == b'\1'
        assert not m.endpoint_in(1)
        nonce = 0
        token = 0x98317265

        def rpc(command, offset=0, count=0, body=b''):
            nonlocal nonce
            nonce += 1
            prefix = struct.pack('<I', nonce)
            request = prefix + struct.pack('<IBHH', token, command, offset, count) + body
            before = len(trace()); symbols(request)
            for _ in range(240):
                step(20)
                if m.read(m.symbols['bluetooth_settings'] + ReplyState.replying.offset, 1) == b'\0':
                    break
            step(20)
            raw = trace()[before:]
            values = []
            at = 0
            while at + 10 <= len(raw):
                packet = raw[at:at + 10]
                if packet[0] == 0xa1 and sum(packet[:-1]) & 255 == packet[-1]:
                    assert packet[8] == 0, 'Reply modified Apple TopCase Fn'
                    values.append(packet[2]); at += 10
                else:
                    at += 1
            # Normal key-release reports may precede the start marker. The
            # native receiver ignores those, then requires an unbroken stream.
            assert 255 in values, (command, values[:5])
            values = values[values.index(255):]
            decoded = bytearray(); value = bits = 0
            groups = 0
            previous = 255
            for symbol in values[1:]:
                if symbol == previous: continue
                previous = symbol
                group = groups; groups += 1
                # The adapter restores the data field after a complete frame.
                if len(decoded) >= 11 and len(decoded) == 15 + struct.unpack_from('<H', decoded, 9)[0]: break
                assert symbol >> 7 == group % 2, (group, symbol)
                value |= (symbol & 127) << bits; bits += 7
                while bits >= 8:
                    decoded.append(value & 255); value >>= 8; bits -= 8
            assert len(decoded) >= 15
            length = struct.unpack_from('<H', decoded, 9)[0]
            assert len(decoded) == length + 15, (len(decoded), length)
            assert decoded[:4] == prefix and decoded[4] == command
            assert struct.unpack_from('<H', decoded, 7)[0] == offset
            assert zlib.crc32(decoded[:-4]) == struct.unpack_from('<I', decoded, len(decoded) - 4)[0]
            return decoded[5], decoded[6], bytes(decoded[11:-4])

        assert rpc(0) == (0, 0, struct.pack('<BHHB', 3, BUNDLE_BYTES, 256, 48))
        assert rpc(6) == (0, 0, b'\x07')
        config_before = m.read(m.symbols['state'], 116)
        assert rpc(7, 0, 4, struct.pack('<I', 45240)) == (0, 0, struct.pack('<I', 45240))
        assert m.read(m.symbols['clock_state'] + 8, 1) == b'\1'
        assert rpc(7, 0, 4, struct.pack('<I', 86400))[0] == 3
        assert rpc(7, 1, 4, struct.pack('<I', 0))[0] == 3
        assert rpc(7, 0, 3, bytes(3))[0] == 3
        assert m.read32(m.symbols['clock_state']) // 60 == 754
        assert m.read(m.symbols['state'], 116) == config_before
        assert m.read32(HOST + 0x5c) == 0, 'Clock sync wrote flash'
        if clock_only:
            from display_types import View
            step(1100)
            assert m.read(m.symbols['frame'] + View.clock.offset, 6) == b'12:34\0'
            assert rpc(7, 0, 4, struct.pack('<I', 86399))[0] == 0
            step(1800)
            assert m.read32(m.symbols['clock_state']) < 5, 'Clock did not wrap at midnight'
            assert rpc(1)[0] == 0
            assert rpc(7, 0, 4, bytes(4))[0] == 1, 'Clock changed during settings session'
            assert rpc(5)[0] == 0
            assert not m.endpoint_in(1)
            return dict(status='passed', candidate_sha256=hashlib.sha256(Path(image).read_bytes()).hexdigest(),
                        uart_clock_to_home=True, crc_checked_time_echo=True, invalid_time_rejected=True,
                        midnight_rollover=True, settings_session_isolation=True, settings_unchanged=True,
                        flash_writes=0, usb_not_enumerated=True, physical_bluetooth_link_tested=False)
        status, phase, snapshot_identity = rpc(1)
        assert (status, phase) == (0, 2)
        if consumer_only:
            # Model the report's actual consumer: data must stay in Constant
            # padding, with the Fn usage and ordinary key fields untouched.
            m.write(m.symbols['transfer'],bytes(range(256)))
            m.write(m.symbols['key_owners']+4,b'\1')
            m.write(m.symbols['key_owners']+0xe1,b'\1')
            before=len(trace());status,phase,payload=rpc(2,0,256)
            assert status==0 and payload==bytes(range(256))
            raw=trace()[before:];packets=[];at=0
            sizes={0xa1:10,0xa3:4,0xa8:7,0xa6:3,0x61:3}
            while at<len(raw):
                size=sizes[raw[at]];packet=raw[at:at+size];assert len(packet)==size
                if packet[0]==0xa1:packets.append(packet)
                at+=size
            assert packets and all(p[1]==2 and p[3:9]==bytes((4,0,0,0,0,0)) for p in packets)
            return {'status':'passed','candidate_sha256':hashlib.sha256(Path(image).read_bytes()).hexdigest(),
                    'all_256_payload_bytes':True,'apple_fn_always_zero':True,
                    'ordinary_keys_and_modifiers_unchanged':True,'data_only_in_constant_padding':True,
                    'physical_bluetooth_link_tested':False}
        parts = []
        for offset in range(0, BUNDLE_BYTES, 256):
            count = min(256, BUNDLE_BYTES - offset)
            status, phase, payload = rpc(2, offset, count)
            assert (status, phase) == (0, 2) and len(payload) == count
            parts.append(payload)
            print(f'Bluetooth snapshot: {offset + count}/{BUNDLE_BYTES} bytes verified', flush=True)
        original = b''.join(parts); validate(original)
        from keyboard_bluetooth import unpack_snapshot
        compressed=bytearray(); compressed_windows=0
        while len(compressed)<BUNDLE_BYTES:
            status,phase,payload=rpc(8,len(compressed),BUNDLE_BYTES-len(compressed))
            assert (status,phase)==(0,2) and len(payload)>=4
            count=struct.unpack_from('<H',payload)[0]
            assert 0<count<=BUNDLE_BYTES-len(compressed)
            compressed.extend(unpack_snapshot(payload[2:],count));compressed_windows+=1
        assert bytes(compressed)==original and compressed_windows<13
        assert rpc(8,0,0)[0]==3 and rpc(8,BUNDLE_BYTES,1)[0]==3
        print(f'Compressed snapshot: {compressed_windows} windows instead of 13 raw windows',flush=True)
        assert snapshot_crc(original) == struct.unpack('<I', snapshot_identity)[0]
        assert rpc(2, BUNDLE_BYTES - 1, 2)[0] == 3
        desired = bytearray(original); desired[119] = (original[119] + 1) % 3
        struct.pack_into('<I', desired, 156, zlib.crc32(desired[:156]))
        assert rpc(3, 119, 1, desired[119:120])[0] == 0
        assert rpc(3, 156, 4, desired[156:160])[0] == 0
        assert m.read(m.symbols['state'] + 107, 1) == bytes((original[119],))
        assert rpc(4, 0, 5, bytes(5))[0] == 2
        assert rpc(4, 0, 5, struct.pack('<IB', snapshot_crc(desired), 0))[0] == 0
        print('Bluetooth RAM Apply verified', flush=True)
        assert rpc(0)[1] == 4
        assert m.read(m.symbols['state'] + 107, 1) == desired[119:120]
        assert m.read(m.symbols['active_slot'], 1) == b'\1'
        assert m.read32(HOST + 0x5c) == 0, 'RAM apply wrote flash'
        assert rpc(5)[0] == 0
        assert rpc(1)[0] == 0
        assert rpc(2, 0, 160)[2] == bytes(desired[:160])
        assert rpc(3, 119, 1, original[119:120])[0] == 0
        assert rpc(3, 156, 4, original[156:160])[0] == 0
        assert rpc(4, 0, 5, struct.pack('<IB', snapshot_crc(original), 1))[0] == 0
        assert rpc(0)[1] == 5
        assert m.read32(HOST + 0x5c) > 0, 'Explicit Save did not write reserved records'
        assert m.read32(HOST + 0x60) == 0, 'Save touched protected code'
        print('Bluetooth Save and protected code verified', flush=True)
        assert m.read(m.symbols['state'] + 107, 1) == original[119:120]
        assert rpc(5)[0] == 0
        assert rpc(1)[0] == 0
        # Data packets preserve held ordinary keys and modifiers. The receiver
        # still recovers a complete CRC-checked response while they are held.
        m.write(m.symbols['key_owners'] + 4, b'\1')
        m.write(m.symbols['key_owners'] + 0xe1, b'\1')
        before = len(trace()); assert rpc(2, 0, 160)[0] == 0
        raw = trace()[before:]
        packets = [raw[i:i+10] for i in range(len(raw)-9) if raw[i]==0xa1 and raw[i+8]==0 and sum(raw[i:i+9])&255==raw[i+9]]
        assert packets and all(p[1]==2 and p[3]==4 and p[8]==0 for p in packets), 'Data stream released a held key/modifier'
        m.write(m.symbols['key_owners'] + 4, b'\0')
        m.write(m.symbols['key_owners'] + 0xe1, b'\0')
        # A physical switch change releases the snapshot before USB can edit.
        m.write32(HOST + 0x204, 1 << 2); step(100)
        assert m.read(m.symbols['transfer'] + BUNDLE_BYTES + 14, 1) == b'\0'
        return {'status': 'passed', 'candidate_sha256': hashlib.sha256(Path(image).read_bytes()).hexdigest(),
                'full_snapshot_uart_roundtrip': True, 'crc_checked_ram_apply_and_readback': True,
                'explicit_save_reserved_records_only': True, 'held_keys_and_modifiers_preserved_during_reply': True,
                'physical_selector_cancels_session': True, 'usb_not_enumerated': True,
                'physical_bluetooth_link_tested': False}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('image', type=Path); p.add_argument('--output', type=Path, required=True)
    a = p.parse_args(); result = run(a.image)
    a.output.write_text(json.dumps(result, indent=2) + '\n'); print(json.dumps(result))
