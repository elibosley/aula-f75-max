"""The desktop can relay fixed power telemetry without opening a settings session."""
import json
from pathlib import Path
import struct
import sys
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import desktop
import hardware_api


class PowerApiTest(unittest.TestCase):
    def test_authorized_read_only_relay_and_origin_identity_guards(self):
        board = 'a' * 64
        calls = []
        snapshot = struct.pack('<BBBBHHIIII', 1, 19, 50, 2, 4000, 12288, 100000, 99900, 123, 7)

        class Keyboard:
            def __init__(self, *args, **kwargs): pass
            def __enter__(self):
                assert self.expected_board == board
                calls.append('open'); return self
            def __exit__(self, *args): calls.append('close')
            def power_snapshot(self): calls.append('power'); return snapshot

        def discover(probe):
            return {'usb': {'present': False, 'available': False, 'board_identity': board},
                    'bluetooth': {'available': True, 'slot': 2, 'access': 'granted', 'board_identity': board}}

        with patch.object(desktop, 'hid_backend', lambda: None), \
             patch.object(desktop, 'bluetooth_status_probe', lambda: 'probe'), \
             patch.object(hardware_api, 'discover', discover), \
             patch.object(hardware_api, 'BluetoothKeyboard', Keyboard), desktop.editor_server() as origin:
            with urlopen(origin + '/api/hardware') as response: token = json.load(response)['csrf']
            body = dict(action='power', transport='auto', expected_transport='bluetooth', expected_slot=2, board_identity=board)

            def request(value, csrf=token, source=origin):
                return Request(origin + '/api/hardware', data=json.dumps(value).encode(), headers={
                    'Origin': source, 'X-F75-CSRF': csrf, 'Content-Type': 'application/json'})

            with urlopen(request(body)) as response: result = json.load(response)
            self.assertEqual(calls, ['open', 'power', 'close'])
            self.assertEqual(result['board_identity'], board)
            self.assertEqual(result['transport'], 'bluetooth')
            self.assertFalse(result['power']['charging'])
            self.assertFalse(result['power']['usb_configured'])
            self.assertNotIn('document', result)
            for value, token_value, source, status in [
                (body, '', origin, 403), (body, token, 'http://foreign.invalid', 403),
                (dict(body, board_identity='b' * 64), token, origin, 409),
                (dict(body, expected_slot=1), token, origin, 409),
                (dict(body, expected_transport='usb'), token, origin, 409)]:
                with self.subTest(status=status), self.assertRaises(HTTPError) as error:
                    urlopen(request(value, token_value, source))
                self.assertEqual(error.exception.code, status)
                error.exception.close()
            self.assertEqual(calls, ['open', 'power', 'close'])


if __name__ == '__main__': unittest.main()
