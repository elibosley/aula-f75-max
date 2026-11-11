#!/usr/bin/env python3
"""Settings sessions over the enrolled Mac Bluetooth helper, without USB."""
import contextlib
import json
import secrets
import struct
import subprocess
import time
import zlib

from keyboard_customize import BUNDLE_BYTES, validate
from keyboard_transport_lock import TransportLock


def snapshot_crc(data):
    # Embedded record CRCs produce a constant CRC residue. Exclude both CRC
    # words from the snapshot identity while validating each record normally.
    return zlib.crc32(data[160:-4], zlib.crc32(data[:156]))


class BluetoothKeyboard:
    def __init__(self, probe, lock_timeout=1.0):
        self.probe = str(probe)
        self.lock = TransportLock(lock_timeout)
        self.token = secrets.randbits(32) or 1
        self.session = False
        self.progress = lambda *args: None

    def __enter__(self):
        self.lock.__enter__()
        try:
            info = self.request(0)['payload']
            if info != struct.pack('<BHHB', 3, BUNDLE_BYTES, 256, 48):
                raise RuntimeError('This Bluetooth settings protocol is unsupported.')
            return self
        except BaseException:
            self.lock.__exit__()
            raise

    def __exit__(self, *exc):
        try:
            if self.session:
                with contextlib.suppress(Exception):
                    self.end()
        finally:
            self.lock.__exit__()

    def request(self, command, offset=0, count=0, body=b''):
        nonce = secrets.token_bytes(4)
        request = nonce + struct.pack('<IBHH', self.token, command, offset, count) + body
        if len(request) > 64:
            raise ValueError('Bluetooth request exceeds its fixed limit.')
        try:
            completed = subprocess.run([self.probe, '--settings-request'],
                input=request.hex() + '\n', capture_output=True, text=True, timeout=30)
        except subprocess.TimeoutExpired as error:
            raise RuntimeError('Bluetooth settings timed out. Read the keyboard before retrying an Apply or Save.') from error
        except OSError as error:
            raise RuntimeError('Could not start the Bluetooth settings helper.') from error
        try:
            host = json.loads(completed.stdout)
        except json.JSONDecodeError as error:
            raise RuntimeError('Bluetooth settings helper returned no valid response.') from error
        if host.get('access') != 'granted':
            raise RuntimeError('Allow F75 Studio in System Settings > Privacy & Security > Input Monitoring, then quit and reopen Studio.')
        if host.get('settings_reply_failure') == 'Constant padding transport not qualified':
            raise RuntimeError('Bluetooth settings are not enabled for this keyboard yet.')
        if completed.returncode or not host.get('settings_reply_verified'):
            raise RuntimeError('No verified Bluetooth settings reply. Keep the Mac unlocked and keyboard connected. Read before retrying Apply or Save.')
        try:
            reply = bytes.fromhex(host['settings_response_hex'])
        except (ValueError, KeyError, TypeError) as error:
            raise RuntimeError('Bluetooth settings reply was malformed.') from error
        if len(reply) < 15 or reply[:4] != nonce or reply[4] != command or struct.unpack_from('<H', reply, 7)[0] != offset:
            raise RuntimeError('Bluetooth settings reply identity did not match.')
        length = struct.unpack_from('<H', reply, 9)[0]
        if length > 256 or len(reply) != length + 15 or zlib.crc32(reply[:-4]) != struct.unpack_from('<I', reply, len(reply) - 4)[0]:
            raise RuntimeError('Bluetooth settings reply CRC or length did not match.')
        if reply[5]:
            reasons = {1: 'Keyboard settings are busy.', 2: 'Settings snapshot CRC did not match.',
                       3: 'Keyboard rejected the settings request.', 4: 'Bluetooth settings session expired or changed.'}
            raise RuntimeError(reasons.get(reply[5], 'Unknown Bluetooth settings error.'))
        return {'phase': reply[6], 'payload': reply[11:-4]}

    def begin(self):
        if self.session:
            self.end()
        self.token = secrets.randbits(32) or 1
        result = self.request(1)
        self.session = True
        if result['phase'] != 2 or len(result['payload']) != 4:
            raise RuntimeError('Bluetooth settings snapshot did not start.')
        return struct.unpack('<I', result['payload'])[0]

    def end(self):
        self.request(5)
        self.session = False

    def read_snapshot(self, expected_crc):
        blocks = []
        for offset in range(0, BUNDLE_BYTES, 256):
            count = min(256, BUNDLE_BYTES - offset)
            block = self.request(2, offset, count)['payload']
            if len(block) != count:
                raise RuntimeError('Bluetooth snapshot block was short.')
            blocks.append(block)
            self.progress('reading', offset + count, BUNDLE_BYTES)
        self.progress('checking')
        data = b''.join(blocks)
        validate(data)
        if snapshot_crc(data) != expected_crc:
            raise RuntimeError('Bluetooth settings snapshot changed during download.')
        return data

    def read(self):
        self.progress('reading')
        crc = self.begin()
        try:
            data = self.read_snapshot(crc)
        except BaseException:
            with contextlib.suppress(Exception):
                self.end()
            raise
        self.end()
        return data

    def apply(self, data, save=False, baseline=None):
        self.progress('preparing')
        validate(data)
        if baseline is not None:
            validate(baseline)
        crc = self.begin()
        commit_started = False
        try:
            if baseline is not None:
                if snapshot_crc(baseline) != crc:
                    raise RuntimeError('Keyboard settings changed since this editor read them. Read the keyboard before applying.')
                current = baseline
            else:
                current = self.read_snapshot(crc)
            # Send only changed windows. The complete candidate still must pass
            # its CRC and both record validators before the board applies it.
            patches = []
            offset = 0
            while offset < BUNDLE_BYTES:
                if current[offset] == data[offset]:
                    offset += 1
                    continue
                end = min(offset + 48, BUNDLE_BYTES)
                while end > offset + 1 and current[end - 1] == data[end - 1]:
                    end -= 1
                patches.append((offset, end))
                offset = end
            sent = 0
            total = sum(end - offset for offset, end in patches)
            for offset, end in patches:
                self.request(3, offset, end - offset, data[offset:end])
                sent += end - offset
                self.progress('sending', sent, total)
            self.progress('saving' if save else 'applying')
            commit_started = True
            self.request(4, 0, 5, struct.pack('<IB', snapshot_crc(data), bool(save)))
            # Commit is never retried automatically. Query the resulting phase
            # instead, because a lost response can follow a successful apply.
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                phase = self.request(0)['phase']
                if phase in (6, 7):
                    raise RuntimeError('Settings validation failed.' if phase == 6 else 'Settings applied, but Save failed.')
                if phase == (5 if save else 4):
                    self.end()
                    return {'applied': True, 'saved': bool(save), 'transport': 'bluetooth'}
                time.sleep(.05)
            raise RuntimeError('Settings completion is unknown. Read before retrying Apply or Save.')
        except BaseException as error:
            with contextlib.suppress(Exception):
                self.end()
            if commit_started and isinstance(error, Exception):
                raise RuntimeError('Apply or Save result is unconfirmed. Read the keyboard before retrying.') from error
            raise

    def host_status(self):
        # A transport reply proves connectivity, but does not report OS-hint
        # evidence or clock state. Do not invent USB diagnostic fields.
        return None

    def sync_clock(self, seconds):
        raise RuntimeError('Bluetooth clock sync is not implemented yet. Use USB for clock sync.')
