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
from webview.menu import Menu, MenuAction, MenuSeparator

import hardware_api
from keyboard_customize import hid_backend


class DesktopState:
    """Keep the native close confirmation in step with unsaved editor work."""
    _window = None
    _pending_settings = False

    def __init__(self):
        from firmware_installer import FirmwareInstaller
        self.installer = FirmwareInstaller()
        self.previews = {}

    def firmware_availability(self):
        return self.installer.availability()

    def firmware_install_status(self):
        state = self.installer.snapshot()
        if self._window is not None:
            self._window.confirm_close = self._pending_settings or state['busy']
        return state

    def start_firmware_install(self):
        if self._pending_settings:
            raise ValueError('Wait for your settings to finish saving before installing firmware.')
        state = self.installer.start()
        if self._window is not None:
            self._window.confirm_close = True
        return state

    def preview_keyboard(self, identifier, command=None, args=None):
        from keyboard_models import model
        if sys.platform != 'darwin':
            raise RuntimeError('The desktop C display simulator is currently available in the macOS build.')
        from serve_native import Session
        model(identifier)
        if identifier not in self.previews:
            self.previews[identifier] = Session('model-preview-' + identifier)
            self.previews[identifier].command('setModel', [identifier])
            self.previews[identifier].command('wheelFeel', [1])
        session = self.previews[identifier]
        with session.lock:
            if command is not None:
                if command not in ('openPage', 'turn', 'press', 'back', 'petTaps', 'visualSettings'):
                    raise ValueError('Unknown simulator control')
                session.command(command, args or [])
            return session.snapshot({'home': True})

    def set_pending(self, pending):
        if type(pending) is not bool:
            raise ValueError('Expected a boolean pending state')
        self._pending_settings = pending
        if self._window is not None:
            self._window.confirm_close = pending or self.installer.snapshot()['busy']


def keyboard_menu(window, origin=None):
    def command(name):
        return lambda: window.evaluate_js(f'window.F75Studio?.{name}()')

    def pane(section):
        return lambda: window.evaluate_js(f'window.F75Studio?.navigate("{section}")')

    return [Menu('Keyboard', [
        MenuAction('Reload Settings', command('reload')),
        MenuAction('Sync Clock', command('clock')),
        MenuAction('Install Custom Firmware', lambda: window.load_url((origin or window.get_current_url().rsplit('/',1)[0]) + '/firmware.html')),
        MenuSeparator(),
        *[MenuAction(title, pane(section)) for title, section in (
            ('Keys', 'keys'), ('Lighting', 'lighting'), ('Devices', 'devices'),
            ('Screen', 'screen'), ('Battery', 'battery'), ('Macros', 'macros'), ('Notifications', 'status'))],
    ])]


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
        state = DesktopState()
        window = webview.create_window('F75 Studio', f'{origin}/hardware.html', width=1120, height=800,
                                       min_size=(780, 580), js_api=state)
        state._window = window
        webview.start(gui='edgechromium' if sys.platform == 'win32' else None,
                      private_mode=True, menu=keyboard_menu(window,origin), localization={
                          'global.quitConfirmation': 'A keyboard operation or settings save is still in progress. Quit anyway?'
                      })


def check(origin, use_keyboard):
    from urllib.request import Request

    hid = hid_backend()
    if sys.platform == 'linux' and hid.__name__ != 'hidraw':
        raise RuntimeError('The Linux desktop package requires the hidraw backend.')
    for asset in ('hardware.html', 'hardware.js', 'hardware.css', 'autosave.js', 'transfer-progress.js', 'studio.js', 'companions.html', 'firmware.html', 'firmware.js', 'firmware.css'):
        with urlopen(f'{origin}/{asset}', timeout=5) as response:
            if not response.read():
                raise RuntimeError(f'Missing desktop asset: {asset}')
    with urlopen(f'{origin}/api/hardware', timeout=5) as response:
        metadata = json.load(response)
    if not metadata['desktop'] or not metadata['layout']:
        raise RuntimeError('Desktop editor API unavailable')
    simulator = 'macOS build required'
    if sys.platform == 'darwin':
        import base64
        import struct
        preview = DesktopState().preview_keyboard('s75pro', 'openPage', ['Menu'])
        image = base64.b64decode(preview['frame'])
        if struct.unpack_from('>II', image, 16) != (135, 240):
            raise RuntimeError('S75 Pro simulator dimensions did not verify')
        simulator = 'passed'
    if use_keyboard:
        request = Request(f'{origin}/api/hardware', data=b'{"action":"read","transport":"auto"}', headers={
            'Origin': origin, 'Content-Type': 'application/json', 'X-F75-CSRF': metadata['csrf']})
        with urlopen(request, timeout=180) as response:
            result = json.load(response)
        if not result['read'] or result['document']['schema'] != 1:
            raise RuntimeError('Keyboard settings read failed')
    if sys.stdout is not None:
        print(json.dumps({'desktop': 'passed', 'keyboard_read': use_keyboard,
                          'hid_backend': hid.__name__, 'bluetooth_status': metadata['bluetooth_status'], 's75_simulator': simulator}))


if __name__ == '__main__':
    main()
