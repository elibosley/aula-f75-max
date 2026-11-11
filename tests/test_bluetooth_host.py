"""Bluetooth host/session contract tests without HID access."""
import contextlib
import json
from pathlib import Path
import struct
import subprocess
import sys
import unittest
from unittest.mock import patch
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from keyboard_bluetooth import BluetoothKeyboard, snapshot_crc


def fixture():
    core = bytearray(160); core[:4] = b'F75S'; core[4] = 6
    for i, name in enumerate([b'USB', b'Laptop', b'Tablet', b'Phone', b'Receiver']):
        core[17 + i * 19:36 + i * 19] = name.ljust(19, b'\0')
    struct.pack_into('<I', core, 156, zlib.crc32(core[:156]))
    custom = bytearray(3072); custom[:4] = b'F75C'; custom[4] = 1
    struct.pack_into('<H', custom, 6, 3072)
    struct.pack_into('<I', custom, 3068, zlib.crc32(custom[:3068]))
    return bytes(core + custom)


class BluetoothHostTest(unittest.TestCase):
    def setUp(self):
        self.live = fixture(); self.staged = None; self.phase = 0; self.calls = []; self.corrupt = False; self.indicator_capability = True
        self.capabilities = 3; self.clock_echo = None
        self.patches = [patch('keyboard_bluetooth.subprocess.run', side_effect=self.helper),
                        patch('keyboard_bluetooth.TransportLock', side_effect=lambda _: contextlib.nullcontext())]
        for item in self.patches: item.start()

    def tearDown(self):
        for item in reversed(self.patches): item.stop()

    def helper(self, arguments, *, input, **kwargs):
        self.assertEqual(arguments, ['probe', '--settings-request'])
        q = bytes.fromhex(input.strip()); nonce = q[:4]
        token, command, offset, count = struct.unpack_from('<IBHH', q, 4)
        self.calls.append(command); payload = b''; status = 0
        if command == 0: payload = struct.pack('<BHHB', 3, 3232, 256, 48)
        elif command == 6:
            if self.indicator_capability: payload = bytes([self.capabilities])
            else: status = 3
        elif command == 7:
            self.assertEqual((offset, count, len(q)), (0, 4, 17))
            payload = q[13:] if self.clock_echo is None else self.clock_echo
        elif command == 1:
            self.staged = bytearray(self.live); self.phase = 2
            payload = struct.pack('<I', snapshot_crc(self.staged))
        elif command == 2: payload = self.staged[offset:offset + count]
        elif command == 3:
            self.assertEqual(len(q), 13 + count)
            self.staged[offset:offset + count] = q[13:]
        elif command == 4:
            self.assertEqual(snapshot_crc(self.staged), struct.unpack_from('<I', q, 13)[0])
            self.live = bytes(self.staged); self.phase = 5 if q[17] else 4
        elif command == 5: self.phase = 0; self.staged = None
        r = nonce + struct.pack('<BBBH H', command, status, self.phase, offset, len(payload)) + payload
        r += struct.pack('<I', zlib.crc32(r) ^ self.corrupt)
        return subprocess.CompletedProcess(arguments, 0, json.dumps({'access':'granted','settings_reply_verified':True,
            'settings_response_hex':r.hex()}), '')

    def test_indicator_capability_and_legacy_unsupported_are_explicit(self):
        with BluetoothKeyboard('probe') as keyboard:
            self.assertTrue(keyboard.indicator_support)
        self.indicator_capability = False
        with BluetoothKeyboard('probe') as keyboard:
            self.assertFalse(keyboard.indicator_support)
        self.assertEqual(self.calls, [0, 6, 0, 6])

    def test_full_read_apply_readback_and_explicit_save(self):
        with BluetoothKeyboard('probe') as keyboard:
            original = keyboard.read(); self.assertEqual(original, self.live)
            desired = bytearray(original); desired[119] = 1
            struct.pack_into('<I', desired, 156, zlib.crc32(desired[:156]))
            result = keyboard.apply(bytes(desired))
            self.assertEqual(result, {'applied': True, 'saved': False, 'transport': 'bluetooth'})
            self.assertEqual(keyboard.read(), desired)
            self.assertEqual(keyboard.apply(original, save=True)['saved'], True)
            self.assertEqual(keyboard.read(), original)
        self.assertEqual(self.calls.count(4), 2, 'Commit was retried')
        self.assertLessEqual(self.calls.count(3), 4, 'Unchanged snapshot was unnecessarily uploaded')

    def test_bad_reply_crc_fails_before_session_or_commit(self):
        self.corrupt = True
        with self.assertRaisesRegex(RuntimeError, 'CRC'):
            with BluetoothKeyboard('probe'): pass
        self.assertEqual(self.calls, [0])

    def test_lost_commit_response_does_not_retry(self):
        normal = self.helper
        def lose(arguments, *, input, **kwargs):
            q = bytes.fromhex(input.strip())
            if q[8] == 4:
                normal(arguments, input=input, **kwargs)
                return subprocess.CompletedProcess(arguments, 1, '{}', '')
            return normal(arguments, input=input, **kwargs)
        with patch('keyboard_bluetooth.subprocess.run', side_effect=lose):
            with BluetoothKeyboard('probe') as keyboard:
                with self.assertRaisesRegex(RuntimeError, 'result is unconfirmed'):
                    keyboard.apply(self.live)
        self.assertEqual(self.calls.count(4), 1)

    def test_editor_baseline_avoids_second_download_and_rejects_stale_edits(self):
        baseline = self.live
        changed = bytearray(baseline); changed[119] = 1
        struct.pack_into('<I', changed, 156, zlib.crc32(changed[:156]))
        self.assertEqual(zlib.crc32(changed), zlib.crc32(baseline))
        self.assertNotEqual(snapshot_crc(changed), snapshot_crc(baseline))
        with BluetoothKeyboard('probe') as keyboard:
            keyboard.apply(bytes(changed), baseline=baseline)
            self.assertNotIn(2, self.calls, 'Apply downloaded the unchanged baseline again')
            before = self.calls.count(4)
            with self.assertRaisesRegex(RuntimeError, 'changed since'):
                keyboard.apply(baseline, baseline=baseline)
            self.assertEqual(self.calls.count(4), before, 'Stale edit reached Commit')

    def test_clock_acknowledges_exact_time_without_a_settings_session(self):
        original = self.live
        with BluetoothKeyboard('probe') as keyboard:
            self.assertTrue(keyboard.clock_support)
            self.assertEqual(keyboard.sync_clock(86399)['seconds'], 86399)
        self.assertEqual(self.calls, [0, 6, 7])
        self.assertEqual(self.live, original)
        self.assertIsNone(self.staged)

    def test_clock_rejects_bad_values_and_legacy_firmware_without_sending(self):
        with BluetoothKeyboard('probe') as keyboard:
            for value in [-1, 86400, True, '123', 1.5]:
                with self.assertRaises(ValueError): keyboard.sync_clock(value)
        self.assertNotIn(7, self.calls)
        for capability in [0, 1]:
            self.capabilities = capability
            with BluetoothKeyboard('probe') as keyboard:
                self.assertFalse(keyboard.clock_support)
                with self.assertRaisesRegex(RuntimeError, 'Update'): keyboard.sync_clock(0)
        self.assertNotIn(7, self.calls)

    def test_clock_requires_exact_verified_reply_and_never_retries(self):
        with BluetoothKeyboard('probe') as keyboard:
            self.clock_echo = struct.pack('<I', 11)
            with self.assertRaisesRegex(RuntimeError, 'not confirmed'): keyboard.sync_clock(12)
            self.assertEqual(self.calls.count(7), 1)
            self.clock_echo = None; self.corrupt = True
            with self.assertRaisesRegex(RuntimeError, 'CRC'): keyboard.sync_clock(12)
            self.assertEqual(self.calls.count(7), 2)

    def test_unknown_capability_stops_before_clock(self):
        self.capabilities = 4
        with self.assertRaisesRegex(RuntimeError, 'Unknown Bluetooth capability'):
            with BluetoothKeyboard('probe'): self.fail('Unknown capability accepted')
        self.assertNotIn(7, self.calls)

    def test_missing_permission_stops_before_a_settings_session(self):
        reply = subprocess.CompletedProcess(['probe'], 0, json.dumps({'access':'unknown'}), '')
        with patch('keyboard_bluetooth.subprocess.run', return_value=reply):
            with self.assertRaisesRegex(RuntimeError, 'Input Monitoring'):
                with BluetoothKeyboard('probe'):
                    self.fail('Unapproved access opened a settings session')
        self.assertEqual(self.calls, [])


if __name__ == '__main__': unittest.main()
