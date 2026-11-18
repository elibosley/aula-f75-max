"""A desktop installation must reject the wrong model or image before erasing."""
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from firmware_installer import FirmwareInstaller, load_bundle
from keyboard_models import identify
from test_flash_protocol import IMAGE, SimulatedRom

S75 = dict(vendor_id=0x0c45, product_id=0x800a, product_string='AULA-S75Pro', path=b's75')


class InstallerRom(SimulatedRom):
    def __init__(self):
        super().__init__()
        self.booted = self.returned = self.closed = False

    def write(self, data):
        if data[:8] == bytes.fromhex('aa42895aff7162cc'):
            self.booted = True
        else:
            super().write(data)

    def command(self, opcode, fields=None):
        if opcode == 7:
            self.returned = True
            return None
        return super().command(opcode, fields)

    def close(self):
        self.closed = True


class FirmwareInstallerTest(unittest.TestCase):
    def test_shared_vendor_product_id_is_not_a_model_match(self):
        with self.assertRaises(ValueError):
            identify([dict(S75, product_string='Other AULA keyboard')])
        self.assertEqual(identify([S75])['id'], 's75pro')
        with self.assertRaises(ValueError):
            identify([S75, dict(S75, product_string='AULA F75 Max')])

    def test_unqualified_and_corrupt_packages_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)
            (path/'release.json').write_text(json.dumps(dict(target='s75pro', qualification='pending')))
            with self.assertRaisesRegex(ValueError, 'no qualified'):
                load_bundle('s75pro', path)
            (path/'release.json').write_text(json.dumps(dict(target='s75pro', qualification='passed', sha256={})))
            (path/'firmware.bin').write_bytes(b'wrong image')
            with self.assertRaisesRegex(ValueError, 'verification failed'):
                load_bundle('s75pro', path)

    def test_release_absence_never_enters_bootloader(self):
        with tempfile.TemporaryDirectory() as temporary:
            installer = FirmwareInstaller(bundle_root=Path(temporary)/'releases', data_root=Path(temporary)/'records')
            with patch('hid.enumerate', return_value=[S75]), patch('firmware_installer.Rom') as rom:
                installer.install()
            rom.assert_not_called()
            self.assertFalse(installer.snapshot()['recovery_required'])
            self.assertEqual(installer.snapshot()['stage'], 'failed_before_erase')

    def test_changed_stock_checksum_stops_before_erase_and_returns(self):
        with tempfile.TemporaryDirectory() as temporary:
            installer = FirmwareInstaller(data_root=temporary)
            rom = InstallerRom()
            with patch('hid.enumerate', return_value=[S75]), \
                    patch('firmware_installer.load_bundle', return_value=(IMAGE, [0x1234])), \
                    patch('firmware_installer.Rom', return_value=rom), patch('firmware_installer.time.sleep'):
                installer.install()
            self.assertTrue(rom.booted and rom.returned and rom.closed)
            self.assertFalse(any(opcode == 4 for opcode, fields in rom.calls))
            self.assertEqual(installer.snapshot()['stage'], 'failed_before_erase')

    def test_programming_runs_existing_verified_protocol_and_retains_receipt(self):
        with tempfile.TemporaryDirectory() as temporary:
            installer = FirmwareInstaller(data_root=temporary)
            rom = InstallerRom()
            with patch('hid.enumerate', return_value=[S75]), \
                    patch('firmware_installer.load_bundle', return_value=(IMAGE, [0x0e8e])), \
                    patch('firmware_installer.Rom', return_value=rom), patch('firmware_installer.time.sleep'), \
                    contextlib.redirect_stdout(io.StringIO()):
                installer.install()
            self.assertEqual(installer.snapshot()['stage'], 'complete')
            self.assertTrue(rom.returned and rom.closed)
            receipt = json.loads(next(Path(temporary).glob('*.json')).read_text())
            self.assertTrue(receipt['program_verified'])
            self.assertEqual(receipt['target'], 's75pro')

    def test_duplicate_clicks_start_one_worker(self):
        installer = FirmwareInstaller()
        with patch('firmware_installer.threading.Thread') as thread:
            installer.start()
            installer.start()
        thread.assert_called_once()
