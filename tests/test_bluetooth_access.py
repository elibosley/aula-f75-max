"""Keep permission requests explicit and fail closed on unknown helper output."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import json, subprocess, unittest
from unittest.mock import patch
from host_display import bluetooth_access

class BluetoothAccessTest(unittest.TestCase):
    def helper(self, state='unknown'):
        return subprocess.CompletedProcess(['probe'], 0, json.dumps({'access':state,'permission_requested':False}), '')

    def test_check_does_not_request_permission(self):
        with patch('host_display.subprocess.run', return_value=self.helper()) as run:
            self.assertEqual(bluetooth_access('probe')['access'], 'unknown')
        self.assertEqual(run.call_args.args[0], ['probe','--check'])

    def test_explicit_request_uses_only_permission_command(self):
        with patch('host_display.subprocess.run', return_value=self.helper()) as run:
            bluetooth_access('probe', request=True)
        self.assertEqual(run.call_args.args[0], ['probe','--request-access'])

    def test_invalid_reply_never_becomes_granted(self):
        for output in ['{}', '[]', '{"access":"other"}', 'not JSON']:
            with self.subTest(output=output), patch('host_display.subprocess.run', return_value=subprocess.CompletedProcess(['probe'],0,output,'')):
                with self.assertRaises(RuntimeError): bluetooth_access('probe')

if __name__ == '__main__': unittest.main()
