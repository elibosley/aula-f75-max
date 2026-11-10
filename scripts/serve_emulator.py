#!/usr/bin/env python3
"""Phone-accessible controls for the actual ARM image on the wired QEMU model."""
import argparse
import base64
from http.server import SimpleHTTPRequestHandler, HTTPServer
import io
import json
from pathlib import Path
import signal
import struct
import threading

from PIL import Image
from system_emulator import System, ROOT, HOST
from test_system_emulator import enumerate_usb


class Emulator:
    def __init__(self, image):
        self.machine = System(image)
        self.identity = enumerate_usb(self.machine)
        self.image_hash = __import__('hashlib').sha256(Path(image).read_bytes()).hexdigest()
        self.frame = Image.new('RGB', (128, 128))
        self.command = None
        self.data = bytearray()
        self.columns = self.rows = None
        self.reports = []
        self.updated_rows = set()
        self.capture()

    def capture(self):
        machine = self.machine
        count = machine.read32(HOST + 4)
        assert count < 2097152, 'SPI capture overflow; restart emulator'
        trace = machine.read(0x60000000, count * 2) if count else b''
        machine.write32(HOST + 0x30, 0)
        for value, dc in zip(trace[::2], trace[1::2]):
            if not dc:
                self.command = value
                self.data.clear()
            else:
                self.data.append(value)
                if self.command in (0x2a, 0x2b) and len(self.data) == 4:
                    if self.command == 0x2a: self.columns = struct.unpack('>HH', self.data)
                    else: self.rows = struct.unpack('>HH', self.data)
                if self.command == 0x2c and self.columns == (2, 129) and self.rows:
                    expected = 128 * (self.rows[1] - self.rows[0] + 1) * 2
                    if len(self.data) == expected:
                        self.updated_rows.update(range(self.rows[0]-1,self.rows[1]))
                        for index, (rgb,) in enumerate(struct.iter_unpack('>H', self.data)):
                            x, y = index % 128, self.rows[0] - 1 + index // 128
                            if 0 <= y < 128:
                                self.frame.putpixel((x,y), (((rgb>>11)&31)*255//31, ((rgb>>5)&63)*255//63, (rgb&31)*255//31))

    def advance(self, duration):
        deadline = self.machine.read32(HOST + 12) + duration * 1000
        while self.machine.read32(HOST + 12) < deadline:
            remaining = (deadline - self.machine.read32(HOST + 12) + 999) // 1000
            self.machine.advance(min(20, max(1, remaining)))
            self.machine.pump()
            for ep in (1, 2, 4):
                packet = self.machine.endpoint_in(ep)
                if packet:
                    self.reports.append(dict(endpoint=ep, data=packet.hex()))
            self.reports = self.reports[-8:]
            self.capture()
        assert self.machine.read32(HOST + 8) == 0, 'Unmodeled hardware access'

    def action(self, name, value=None):
        machine = self.machine
        if name == 'turn':
            assert value in (-1, 1)
            sequence = [3, 2, 0, 1, 3] if value > 0 else [3, 1, 0, 2, 3]
            for state in sequence:
                machine.write32(HOST + 0x200, (1 << 10) | ((state & 1) << 2) | ((state & 2) << 2))
                self.advance(5)
        elif name in ('press', 'back'):
            if 'f75_wheel_matrix_row' in machine.symbols:
                address = HOST + 0x100 + machine.symbols['f75_wheel_matrix_row'] * 4
                down, up = 1 << machine.symbols['f75_wheel_matrix_col'], 0
            else:
                address, down, up = HOST + 0x204, 1 << 2, (1 << 2) | (1 << 17)
            machine.write32(address, down)
            self.advance(720 if name == 'back' else 60)
            machine.write32(address, up)
            self.advance(60)
        elif name == 'tap':
            assert value in ('a', 'caps', 'ctrl', 'cmd')
            row, col = {'a':(1,3), 'caps':(0,3), 'ctrl':(0,5), 'cmd':(2,5)}[value]
            machine.write32(HOST + 0x100 + row * 4, 1 << col)
            self.advance(20)
            machine.write32(HOST + 0x100 + row * 4, 0)
            self.advance(20)
        elif name == 'tick':
            self.advance(100)
        else:
            raise ValueError('Unknown emulator action')
        self.advance(100)

    def state(self):
        buffer = io.BytesIO()
        self.frame.save(buffer, format='PNG')
        machine = self.machine
        return dict(image_sha256=self.image_hash, png=base64.b64encode(buffer.getvalue()).decode(),
                    uptime_ms=machine.read32(HOST + 12) // 1000,
                    frames=machine.read32(machine.symbols['complete_frames']),
                    scans=machine.read32(machine.symbols['f75_matrix_scans']),
                    page=machine.read(machine.symbols['navigation'], 1)[0], cursor=machine.read(machine.symbols['navigation']+1,1)[0], reports=self.reports,
                    hardware_writes=False, core='Cortex-M0 / QEMU 10.1.3')


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT / 'ui'), **kwargs)

    def reply(self, status, value):
        data = json.dumps(value).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == '/api/state':
            try:
                self.reply(200, self.server.emulator.state())
            except Exception as error:
                self.reply(500, dict(error=str(error)))
        elif self.path in ('/', '/emulator.html', '/emulator.css', '/style.css'):
            if self.path == '/': self.path = '/emulator.html'
            super().do_GET()
        else:
            self.send_error(404)

    def do_POST(self):
        origin = self.headers.get('Origin')
        if (origin and origin != 'http://' + self.headers.get('Host', '')) or self.headers.get('X-F75-Action') != '1':
            self.send_error(403); return
        if self.path != '/api/action':
            self.send_error(404); return
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 256: raise ValueError('Invalid request size')
            command = json.loads(self.rfile.read(length))
            self.server.emulator.action(command['action'], command.get('value'))
            self.reply(200, self.server.emulator.state())
        except (ValueError, KeyError, AssertionError) as error:
            self.reply(400, dict(error=str(error)))
        except Exception as error:
            self.reply(500, dict(error=str(error), recovery='Restart the ARM emulator service'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('image', type=Path, nargs='?')
    parser.add_argument('--bind', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8788)
    args = parser.parse_args()
    if args.image is None:
        args.image = ROOT / json.loads((ROOT / 'analysis/emulator-image.json').read_text())['image']
    build = json.loads(args.image.with_suffix('.json').read_text())
    if build.get('profile') != 'full_ui':
        raise SystemExit('Interactive screen requires a full_ui build; USB-only intentionally omits the display')
    emulator = Emulator(args.image)
    server = HTTPServer((args.bind, args.port), Handler)
    server.emulator = emulator
    def stop(*_): raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, stop)
    try:
        print(f'ARM emulator listening on {args.bind}:{args.port}; image {emulator.image_hash}', flush=True)
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        emulator.machine.close()


if __name__ == '__main__':
    main()
