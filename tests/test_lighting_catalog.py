"""Expanded effects preserve legacy records and reject unsupported writes."""
import json
from pathlib import Path
import struct
import subprocess
import sys
import unittest
import zlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from keyboard_customize import decode, encode
from test_bluetooth_host import fixture


class LightingCatalogTest(unittest.TestCase):
    def document(self, count):
        data = bytearray(fixture()); data[128] = count
        struct.pack_into('<I', data, 156, zlib.crc32(data[:156]))
        return decode(bytes(data))

    def test_stable_catalog_and_firmware_names(self):
        effects = json.loads((ROOT / 'ui/lighting-effects.json').read_text())
        self.assertEqual([x['id'] for x in effects], list(range(25)))
        self.assertEqual([x['name'] for x in effects[:5]], ['Still', 'Tidal', 'Rain', 'Trails', 'Constellation'])
        subprocess.run([sys.executable, str(ROOT / 'scripts/generate_lighting_catalog.py'), '--check'], check=True)

    def test_all_effects_round_trip_on_supported_firmware(self):
        for effect in range(25):
            document = self.document(25); document['lighting']['effect'] = effect
            actual = decode(encode(document))
            self.assertEqual(actual['lighting']['effect'], effect)
            self.assertEqual(actual['lighting_effect_count'], 25)
        for invalid in (25, -1, True, 1.5):
            document = self.document(25); document['lighting']['effect'] = invalid
            with self.subTest(invalid=invalid), self.assertRaises(ValueError): encode(document)

    def test_legacy_and_unknown_support_fail_closed(self):
        for capability in (0, 4, 26, 255):
            document = self.document(capability)
            self.assertEqual(document['lighting_effect_count'], 5)
            for effect in range(5):
                document['lighting']['effect'] = effect
                self.assertEqual(decode(encode(document))['lighting']['effect'], effect)
            # Editable JSON metadata cannot expand a legacy board's support.
            document['lighting_effect_count'] = 25
            document['lighting']['effect'] = 5
            with self.assertRaisesRegex(ValueError, 'expanded lighting firmware'): encode(document)


if __name__ == '__main__':
    unittest.main()
