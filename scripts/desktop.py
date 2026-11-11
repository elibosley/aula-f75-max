#!/usr/bin/env python3
"""F75 Studio desktop editor for macOS, Windows, and Linux."""
import argparse
from contextlib import contextmanager
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sys
from threading import Thread
from urllib.request import urlopen

import webview

import hardware_api
from keyboard_customize import hid_backend


def bluetooth_status_probe():
    if sys.platform != 'darwin':
        return None
    directory = (Path(sys.executable).resolve().parent.parent / 'Helpers'
                 if getattr(sys, 'frozen', False) else hardware_api.ROOT / '.runtime')
    executable = directory / 'F75 Wireless Probe.app/Contents/MacOS/F75WirelessProbe'
    return executable if executable.is_file() else None


class EditorRequest(SimpleHTTPRequestHandler):
    def setup(self):
        self.request.settimeout(5)
        super().setup()

    def log_message(self, format, *args):
        pass

    def end_headers(self):
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "frame-ancestors 'none'; connect-src 'self'")
        super().end_headers()

    def do_GET(self):
        if self.headers.get('Host') != f'127.0.0.1:{self.server.server_port}':
            self.send_error(403)
        elif not hardware_api.handle(self):
            super().do_GET()

    def do_POST(self):
        if not hardware_api.handle(self):
            self.send_error(404)

    def list_directory(self, path):
        self.send_error(404)
        return None


@contextmanager
def editor_server():
    # macOS HIDAPI schedules its manager on the importing thread's run loop.
    # Initialize it here so it outlives the individual HTTP request threads.
    hid_backend()
    handler = partial(EditorRequest, directory=hardware_api.ROOT / 'ui')
    with ThreadingHTTPServer(('127.0.0.1', 0), handler) as server:
        server.desktop = True
        server.bluetooth_status_probe = bluetooth_status_probe()
        server.daemon_threads = False
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield f'http://127.0.0.1:{server.server_port}'
        finally:
            server.shutdown()
            thread.join()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--check', action='store_true', help='Check bundled assets and API without a keyboard')
    mode.add_argument('--check-keyboard', action='store_true', help='Read the connected keyboard through the desktop API')
    options = parser.parse_args()
    with editor_server() as origin:
        if options.check or options.check_keyboard:
            check(origin, options.check_keyboard)
            return
        webview.settings['ALLOW_DOWNLOADS'] = True
        webview.create_window('F75 Studio', f'{origin}/hardware.html', width=1260, height=880,
                              min_size=(780, 580))
        webview.start(gui='edgechromium' if sys.platform == 'win32' else None, private_mode=True)


def check(origin, use_keyboard):
    from urllib.request import Request

    hid = hid_backend()
    if sys.platform == 'linux' and hid.__name__ != 'hidraw':
        raise RuntimeError('The Linux desktop package requires the hidraw backend.')
    for asset in ('hardware.html', 'hardware.js', 'hardware.css', 'transfer-progress.js', 'studio.js', 'companions.html'):
        with urlopen(f'{origin}/{asset}', timeout=5) as response:
            if not response.read():
                raise RuntimeError(f'Missing desktop asset: {asset}')
    with urlopen(f'{origin}/api/hardware', timeout=5) as response:
        metadata = json.load(response)
    if not metadata['desktop'] or not metadata['layout']:
        raise RuntimeError('Desktop editor API unavailable')
    if use_keyboard:
        request = Request(f'{origin}/api/hardware', data=b'{"action":"read","transport":"auto"}', headers={
            'Origin': origin, 'Content-Type': 'application/json', 'X-F75-CSRF': metadata['csrf']})
        with urlopen(request, timeout=180) as response:
            result = json.load(response)
        if not result['read'] or result['document']['schema'] != 1:
            raise RuntimeError('Keyboard settings read failed')
    if sys.stdout is not None:
        print(json.dumps({'desktop': 'passed', 'keyboard_read': use_keyboard,
                          'hid_backend': hid.__name__, 'bluetooth_status': metadata['bluetooth_status']}))


if __name__ == '__main__':
    main()
