#!/usr/bin/env python3
"""Run the unmodified linked image on the F75 QEMU Cortex-M0 model.

The factory ROM is an explicit stop boundary. No physical USB is opened.
"""
import hashlib
import json
import os
from pathlib import Path
import socket
import struct
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
QEMU = ROOT / 'builddeps/qemu-build/qemu-system-arm'
NM = ROOT / 'builddeps/arm-toolchain/bin/arm-none-eabi-nm'
USB = 0x4005c000
HOST = 0x4007f000


def symbols(elf):
    result = {}
    for line in subprocess.check_output([str(NM), '-n', str(elf)], text=True).splitlines():
        fields = line.split()
        if len(fields) == 3:
            result[fields[2]] = int(fields[0], 16)
    return result


class System:
    def __init__(self, image, ahbcp=0, held=False, magic=False, symbols_file=None, factory_rom=False):
        self.image = Path(image).resolve()
        self.symbols = symbols(symbols_file or self.image.with_suffix('.elf'))
        self.tmp = tempfile.TemporaryDirectory(prefix='f75-')
        self.folder = Path(self.tmp.name)
        self.log = (self.folder / 'qemu.log').open('w+')
        self.process = subprocess.Popen([
            str(QEMU), '-M', 'f75max', '-kernel', str(self.image),
            '-display', 'none', '-serial', 'none', '-monitor', 'none',
            '-S', '-icount', 'shift=4,align=off,sleep=off',
            '-qtest', f'unix:{self.folder}/test,server=on,wait=off',
            '-qtest-log', '/dev/null',
            '-gdb', f'unix:{self.folder}/gdb,server=on,wait=off',
        ], stdout=self.log, stderr=self.log)
        try:
            self.gdb = self.connect('gdb')
            self.test = self.connect('test')
            self._gdb_buffer=bytearray();self._qtest_buffer=bytearray()
            self.gdb.settimeout(8)
            self.test.settimeout(5)
            self.packet('qSupported')
            self.packet('?')
            if factory_rom:
                rom = (ROOT / 'analysis/factory-rom/sn32f29x-boot.bin').read_bytes()
                assert hashlib.sha256(rom).hexdigest() == '06508333749a88ac1251497563015e4709606842e3c0ad304cdcf2eb7951077c'
                for offset in range(0, len(rom), 512):
                    chunk = rom[offset:offset+512]
                    assert self.packet(f'M{0x1fff0000+offset:x},{len(chunk):x}:' + chunk.hex()) == 'OK'
                # ROM identity branch and option word agree with chip=5,
                # family=32, options=FFFF, CS1=5A5A. Chip ID is inferred here.
                for address, value in [(0x1fff2c00, 0x3258), (0x1fff2000, 0x5a5affff)]:
                    assert self.packet(f'M{address:x},4:' + struct.pack('<I', value).hex()) == 'OK'
            self.write32(HOST + 0x10, ahbcp)
            self.write32(HOST + 0x204, (1 << 2) | (0 if held else 1 << 17))
            if 'f75_wheel_matrix_row' in self.symbols:
                self.write32(HOST + 0x204, 1 << 2)  # wired fixture asserts active-low charging; wheel uses the matrix
                self.write32(HOST + 0x100 + self.symbols['f75_wheel_matrix_row'] * 4,
                             (1 << self.symbols['f75_wheel_matrix_col']) if held else 0)
            self.write(0x20007ffc, struct.pack('<I', 0xdeadbeef if magic else 0))
        except Exception:
            self.close()
            raise
        self.checkpoints = []
        self.breakpoints = set()
        self.poll_checkpoint = 'housekeeping_task_user'

    def connect(self, name):
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            sock = socket.socket(socket.AF_UNIX)
            try:
                sock.connect(str(self.folder / name))
                return sock
            except (FileNotFoundError, ConnectionRefusedError):
                sock.close()
                if self.process.poll() is not None:
                    self.log.seek(0)
                    raise RuntimeError(self.log.read())
                time.sleep(.02)
        raise TimeoutError(name)

    def response(self):
        buf=self._gdb_buffer
        while True:
            start=buf.find(b'$')
            if start>=0:
                if start:del buf[:start]
                end=buf.find(b'#',1)
                if end>=0 and len(buf)>=end+3:
                    payload=bytes(buf[1:end]);checksum=bytes(buf[end+1:end+3]);del buf[:end+3]
                    assert int(checksum,16)==sum(payload)&255
                    self.gdb.sendall(b'+');return payload.decode()
            elif buf:buf.clear() # ACKs precede the next packet.
            chunk=self.gdb.recv(65536)
            if not chunk:raise RuntimeError('QEMU GDB disconnected')
            buf.extend(chunk)

    def packet(self, text):
        data = text.encode()
        self.gdb.sendall(b'$' + data + b'#' + f'{sum(data) & 255:02x}'.encode())
        return self.response()

    def command(self, cmd):
        self.test.sendall(cmd.encode()+b'\n')
        buf=self._qtest_buffer
        while True:
            end=buf.find(b'\n')
            if end>=0:
                result=bytes(buf[:end]);del buf[:end+1]
                fields=result.decode().split();assert fields[0]=='OK',result
                return fields[1:]
            chunk=self.test.recv(65536)
            if not chunk:raise RuntimeError('QEMU qtest disconnected')
            buf.extend(chunk)

    def read32(self, address):
        return int(self.command(f'readl {address:#x}')[0], 16)

    def write32(self, address, value):
        self.command(f'writel {address:#x} {value:#x}')

    def read(self, address, length):
        return bytes.fromhex(self.command(f'read {address:#x} {length:#x}')[0][2:])

    def write(self, address, data):
        self.command(f'write {address:#x} {len(data):#x} 0x{data.hex()}')

    def pc(self):
        registers = bytes.fromhex(self.packet('g'))
        return struct.unpack_from('<I', registers, 15 * 4)[0]

    def breakpoint(self, address):
        address &= ~1
        assert self.packet(f'Z1,{address:x},2') == 'OK'
        self.breakpoints.add(address)

    def resume(self):
        try:
            result = self.packet('c')
        except TimeoutError:
            self.gdb.sendall(b'\x03')
            result = self.response()
            raise TimeoutError(f'Firmware did not reach checkpoint; PC={self.pc():#x}, stop={result}')
        return result

    def until(self, name):
        address = self.symbols[name] if isinstance(name, str) else name
        if self.pc() == address:
            self.packet('s')
        self.breakpoint(address)
        result = self.resume()
        pc = self.pc()
        self.packet(f'z1,{address:x},2')
        self.breakpoints.discard(address)
        assert pc == address, (name, hex(pc), result)
        self.checkpoints.append(str(name))

    def cycles(self, count=1, name='housekeeping_task_user'):
        for _ in range(count):
            self.until(name)
            # Continue from the breakpoint; QEMU steps over a removed breakpoint.

    def event(self, flags):
        self.write32(HOST, flags)

    def pump(self, flags=0):
        if flags:
            self.event(flags)
        self.until(self.poll_checkpoint)

    def advance(self, milliseconds):
        assert 0 < milliseconds <= 10000
        start = self.read32(HOST + 12)
        self.write32(HOST + 0x20, milliseconds)
        self.resume()
        elapsed = (self.read32(HOST + 12) - start) & 0xffffffff
        assert elapsed >= milliseconds * 1000, ('early debug stop', elapsed)
        return elapsed

    def endpoint_in(self, ep):
        ctl = self.read32(USB + 0x18 + ep * 4)
        if ctl >> 29 & 3 != 1:
            return None
        offset = self.read32(USB + 0x48 + (ep - 1) * 4)
        packet = self.read(USB + 0x100 + offset, ctl & 511) if ctl & 511 else b''
        self.write32(USB + 0x18 + ep * 4, 0x80000000)
        self.pump(1 << (8 + ep - 1))
        return packet

    def endpoint_out(self, ep, data):
        ctl = self.read32(USB + 0x18 + ep * 4)
        assert ctl >> 29 & 3 == 1, ('OUT endpoint not ready', ep, hex(ctl))
        offset = self.read32(USB + 0x48 + (ep - 1) * 4)
        self.write(USB + 0x100 + offset, data)
        self.write32(USB + 0x18 + ep * 4, 0x80000000 | len(data))
        self.pump(1 << (8 + ep - 1))

    def control(self, request_type, request, value=0, index=0, length=0):
        self.write(USB + 0x100, struct.pack('<BBHHH', request_type, request, value, index, length))
        self.pump(1 << 23)
        data = bytearray()
        if request_type & 0x80:
            for _ in range(128):
                ctl = self.read32(USB + 0x18)
                assert ctl >> 29 & 3 == 1, ('EP0 not ACK', hex(ctl))
                count = ctl & 511
                data.extend(self.read(USB + 0x100, count) if count else b'')
                self.write32(USB + 0x18, 0x80000000)
                self.pump(1 << 22)
                if count < 64 or len(data) >= length:
                    break
            else:
                raise RuntimeError('Unbounded EP0 IN transfer')
            self.write32(USB + 0x18, 0x80000000)
            self.pump(1 << 21)  # host OUT status ZLP
        else:
            assert length == 0, 'control OUT data stage is not implemented'
            assert self.read32(USB + 0x18) & 511 == 0
            self.write32(USB + 0x18, 0x80000000)
            self.pump(1 << 22)  # host IN status ZLP
        return bytes(data)

    def control_out(self, request_type, request, data, value=0, index=0):
        assert not request_type & 0x80 and len(data) <= 64
        self.write(USB + 0x100, struct.pack('<BBHHH', request_type, request, value, index, len(data)))
        self.pump(1 << 23)
        self.write(USB + 0x100, data)
        self.write32(USB + 0x18, 0x80000000 | len(data))
        self.pump(1 << 21)
        assert self.read32(USB + 0x18) & 511 == 0
        self.write32(USB + 0x18, 0x80000000)
        self.pump(1 << 22)

    def close(self):
        for conn in [getattr(self, 'gdb', None), getattr(self, 'test', None)]:
            if conn:
                conn.close()
        if hasattr(self, 'process') and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=3)
        if hasattr(self, 'log'):
            self.log.close()
        if hasattr(self, 'tmp'):
            self.tmp.cleanup()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('image', type=Path)
    parser.add_argument('--ahbcp', type=int, default=0)
    parser.add_argument('--until', default='protocol_pre_init')
    args = parser.parse_args()
    with System(args.image, ahbcp=args.ahbcp) as machine:
        machine.until('main')
        machine.until(args.until)
        print(json.dumps(dict(checkpoints=machine.checkpoints,
                              unmodeled_accesses=machine.read32(HOST + 8),
                              usb_cfg=hex(machine.read32(USB + 0x10))), indent=2))
