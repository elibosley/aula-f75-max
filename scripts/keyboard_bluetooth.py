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
from bluetooth_dictionary import DICTIONARY3
from keyboard_transport_lock import TransportLock


def snapshot_crc(data):
    # Embedded record CRCs produce a constant CRC residue. Exclude both CRC
    # words from the snapshot identity while validating each record normally.
    return zlib.crc32(data[160:-4], zlib.crc32(data[:156]))


def unpack_snapshot(data, expected, codec=1, offset=0):
    if type(expected) is not int or not 0 < expected <= BUNDLE_BYTES:
        raise RuntimeError('Invalid compressed snapshot size.')
    out = bytearray()
    at = 0
    while at < len(data):
        token = data[at]; at += 1
        if codec>=2 and token==128:
            if len(data)-at<2: raise RuntimeError('Compressed zero span was truncated.')
            count=struct.unpack_from('<H',data,at)[0];at+=2
            if not count or count>expected-len(out): raise RuntimeError('Compressed zero span overflows its declared size.')
            out.extend(bytes(count));continue
        count = (token & 127) + 1
        if count > expected - len(out):
            raise RuntimeError('Compressed settings window overflows its declared size.')
        size = 1 if token & 128 else count
        if size > len(data) - at:
            raise RuntimeError('Compressed settings token was truncated.')
        out.extend(bytes([data[at]]) * count if token & 128 else data[at:at + count])
        at += size
    if len(out) != expected:
        raise RuntimeError('Compressed settings window was incomplete.')
    if codec==3:
        if type(offset) is not int or not 0<=offset<=BUNDLE_BYTES-expected: raise RuntimeError('Dictionary window offset is invalid.')
        out=bytearray(a^b for a,b in zip(out,DICTIONARY3[offset:offset+expected]))
    return bytes(out)


class BluetoothKeyboard:
    def __init__(self, probe, lock_timeout=1.0, *, fast=False):
        self.probe = str(probe)
        self.lock = TransportLock(lock_timeout)
        self.token = secrets.randbits(32) or 1
        self.session = False
        self.progress = lambda *args: None
        self.indicator_support = False
        self.clock_support = False
        self.compressed_read_support = False
        self.expected_board = None
        self.prefer_fast=fast; self.fast_mode=False; self._verified=None
        self.fast_snapshot_codec=1
        self.fast_patch_version=1

    def __enter__(self):
        self.lock.__enter__()
        try:
            if self.prefer_fast:
                check=subprocess.run([self.probe,'--check'],capture_output=True,text=True,timeout=5)
                if check.returncode: raise RuntimeError('Bluetooth capability check failed.')
                value=json.loads(check.stdout)
                if value.get('access')!='granted': raise RuntimeError('Allow F75 Studio in Mac Input Monitoring to use Bluetooth.')
                version=value.get('fast_settings_version',0)
                if type(version) is not int or version not in (0,1): raise RuntimeError('Unknown fast Bluetooth capability.')
                if version==1:
                    codec=value.get('fast_snapshot_codec',1)
                    if type(codec) is not int or codec not in (1,2,3): raise RuntimeError('Unknown fast snapshot codec.')
                    self.fast_snapshot_codec=codec
                    version=value.get('fast_patch_version',1)
                    if type(version) is not int or version not in (1,2): raise RuntimeError('Unknown fast patch version.')
                    self.fast_patch_version=version
                    self.fast_mode=True;self.indicator_support=True;self.clock_support=True;self.compressed_read_support=True
                    return self
            info = self.request(0)['payload']
            if info != struct.pack('<BHHB', 3, BUNDLE_BYTES, 256, 48):
                raise RuntimeError('This Bluetooth settings protocol is unsupported.')
            capability = self.request(6, allow_unsupported=True)['payload']
            if len(capability) > 1 or (capability and capability[0] & ~7):
                raise RuntimeError('Unknown Bluetooth capability.')
            flags = capability[0] if capability else 0
            self.indicator_support = bool(flags & 1)
            self.clock_support = bool(flags & 2)
            self.compressed_read_support = bool(flags & 4)
            return self
        except BaseException:
            self.lock.__exit__()
            raise

    def __exit__(self, *exc):
        try:
            # A failed fast reply never sends a legacy cleanup request. Its
            # bounded snapshot expires on the board; diagnose before new RPCs.
            if self.session and not (exc[0] and self.fast_mode):
                with contextlib.suppress(Exception):
                    self.end()
        finally:
            self.lock.__exit__()

    def request(self, command, offset=0, count=0, body=b'', *, allow_unsupported=False):
        nonce = secrets.token_bytes(4)
        request = nonce + struct.pack('<IBHH', self.token, command, offset, count) + body
        if len(request) > 64:
            raise ValueError('Bluetooth request exceeds its fixed limit.')
        return self._exchange([self.probe,'--settings-request'],request,command,offset,allow_unsupported)

    def request_fast(self, command, offset=0, body=b'', nonce=None):
        if command not in (9,10) or len(body)>48: raise ValueError('Invalid fast Bluetooth request.')
        nonce=nonce or struct.pack('<I',secrets.randbits(32) or 1)
        request=nonce+bytes([command])+struct.pack('<H',offset)+body
        return self._exchange([self.probe,'--fast-settings-request'],request,command,offset,False)

    def _exchange(self, arguments, request, command, offset, allow_unsupported):
        self._verified=None
        nonce=request[:4]
        try:
            if self.expected_board:arguments.extend(('--board',self.expected_board))
            completed = subprocess.run(arguments,
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
            if allow_unsupported and command == 6 and reply[5] == 3:
                return {'phase': reply[6], 'payload': b''}
            reasons = {1: 'Keyboard settings are busy.', 2: 'Settings snapshot CRC did not match.',
                       3: 'Keyboard rejected the settings request.', 4: 'Bluetooth settings session expired or changed.',
                       5: 'Settings applied, but Save failed.'}
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
        if self.compressed_read_support:
            return self.read_compressed_snapshot(expected_crc)
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

    def read_compressed_snapshot(self, expected_crc):
        blocks = bytearray()
        while len(blocks) < BUNDLE_BYTES:
            remaining = BUNDLE_BYTES - len(blocks)
            payload = self.request(8, len(blocks), remaining)['payload']
            if len(payload) < 4:
                raise RuntimeError('Compressed settings window was short.')
            count = struct.unpack_from('<H', payload)[0]
            if not 0 < count <= remaining:
                raise RuntimeError('Compressed settings window exceeds the snapshot.')
            block = unpack_snapshot(payload[2:], count)
            blocks.extend(block)
            self.progress('reading', len(blocks), BUNDLE_BYTES)
        data = bytes(blocks)
        self.progress('checking')
        validate(data)
        if snapshot_crc(data) != expected_crc:
            raise RuntimeError('Bluetooth settings snapshot changed during download.')
        return data

    def read_fast(self):
        self.token=secrets.randbits(32) or 1;nonce=struct.pack('<I',self.token)
        data=bytearray();identity=None;self.session=True
        while len(data)<BUNDLE_BYTES:
            body=bytes([self.fast_snapshot_codec]) if self.fast_snapshot_codec>=2 else b''
            reply=self.request_fast(9,len(data),body,nonce=nonce);payload=reply['payload']
            if len(payload)<10 or payload[0]!=self.fast_snapshot_codec or payload[1]&~7: raise RuntimeError('Fast Bluetooth snapshot format is unsupported.')
            crc,count=struct.unpack_from('<IH',payload,2)
            if identity is not None and identity!=crc: raise RuntimeError('Fast Bluetooth snapshot changed.')
            identity=crc
            if not 0<count<=BUNDLE_BYTES-len(data): raise RuntimeError('Invalid fast Bluetooth window size.')
            data.extend(unpack_snapshot(payload[8:],count,self.fast_snapshot_codec,len(data)));self.progress('reading',len(data),BUNDLE_BYTES)
            if reply['phase']!=(0 if len(data)==BUNDLE_BYTES else 2): raise RuntimeError('Fast Bluetooth snapshot phase is invalid.')
        result=bytes(data);validate(result)
        if snapshot_crc(result)!=identity: raise RuntimeError('Fast Bluetooth snapshot CRC differs.')
        self.session=False
        return result

    def read(self):
        self.progress('reading')
        if self.fast_mode:
            try:return self.read_fast()
            except BaseException:
                self.session=False
                raise
        crc = self.begin()
        try:
            data = self.read_snapshot(crc)
        except BaseException:
            with contextlib.suppress(Exception):
                self.end()
            raise
        self.end()
        return data

    def verify(self, data):
        """Check the live, encoded snapshot without downloading unchanged blocks."""
        validate(data)
        if self._verified==data:
            self._verified=None
            return data
        self.progress('verifying')
        actual_crc = self.begin()
        try:
            if actual_crc != snapshot_crc(data):
                raise RuntimeError('Settings snapshot CRC differs; read the keyboard before trying again.')
        finally:
            self.end()
        return data

    def apply(self, data, save=False, baseline=None):
        self.progress('preparing')
        validate(data)
        if baseline is not None:
            validate(baseline)
        if self.fast_mode:
            if baseline is None: baseline=self.read_fast()
            patch=bytearray(struct.pack('<I',snapshot_crc(baseline)));at=0
            while at<BUNDLE_BYTES-4:
                if 156<=at<160 or baseline[at]==data[at]: at+=1;continue
                end=at+1;limit=min(BUNDLE_BYTES-4,156 if at<156 else BUNDLE_BYTES-4)
                while end<limit and data[end]!=baseline[end] and end-at<40:end+=1
                patch.extend(struct.pack('<HB',at,end-at));patch.extend(data[at:end]);at=end
            if len(patch)<=48:
                if self.fast_patch_version==2 and len(patch)==8 and patch[6]==1:
                    position=struct.unpack_from('<H',patch,4)[0]
                    if 114<=position<=121 or 125<=position<=127:
                        patch=patch[:4]+bytes([position,data[position]])
                self.progress('saving' if save else 'applying')
                # An uncertain atomic commit is never retried or sent on USB.
                reply=self.request_fast(10,int(bool(save)),bytes(patch))
                if reply['phase']!=(5 if save else 4) or reply['payload']!=struct.pack('<I',snapshot_crc(data)):
                    raise RuntimeError('Fast Apply/Save result is unconfirmed. Read before trying again.')
                self._verified=bytes(data)
                return {'applied':True,'saved':bool(save),'transport':'bluetooth'}
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
        if type(seconds) is not int or not 0 <= seconds < 86400:
            raise ValueError('Clock needs seconds since local midnight')
        if not self.clock_support:
            raise RuntimeError('Update the keyboard firmware for Bluetooth clock sync.')
        expected = struct.pack('<I', seconds)
        if self.request(7, count=4, body=expected)['payload'] != expected:
            raise RuntimeError('Bluetooth clock synchronization not confirmed.')
        return {'clock_synced': True, 'seconds': seconds, 'transport': 'bluetooth'}
