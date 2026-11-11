"""Notification integrations use the chosen transport without a USB fallback."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import contextlib
import io
import unittest
from unittest.mock import patch
import host_display


class NotificationTest(unittest.TestCase):
    def test_bluetooth_notification_does_not_open_usb(self):
        arguments = ['host_display', '--transport', 'bluetooth', '--probe', '/test/probe',
                     'notify', 'Download complete', '--seconds', '10']
        with patch('sys.argv', arguments), patch.object(host_display, 'Keyboard') as usb, \
                patch.object(host_display, 'bluetooth_display', return_value={'supported': True}) as send, \
                contextlib.redirect_stdout(io.StringIO()):
            host_display.main()
        usb.assert_not_called()
        send.assert_called_once_with(host_display.Path('/test/probe'), 'set', 'Download complete', 10)

    def test_bluetooth_requires_explicit_enrolled_helper(self):
        with patch('sys.argv', ['host_display', '--transport', 'bluetooth', 'notify', 'Hello']), \
                patch.object(host_display, 'Keyboard') as usb, contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as error:
                host_display.main()
        self.assertEqual(error.exception.code, 1)
        usb.assert_not_called()

    def test_notification_payload_rejects_unsupported_text_and_duration(self):
        for text, seconds in [('', 20), ('x' * 21, 20), ('Hello\n', 20), ('Hi ☀', 20), ('Hi', 0), ('Hi', 61)]:
            with self.subTest(text=text, seconds=seconds), self.assertRaises(ValueError):
                host_display.payload('set', text, seconds)
        self.assertEqual(len(host_display.payload('set', 'Meeting in 5 min', 30)), 24)


if __name__ == '__main__':
    unittest.main()
