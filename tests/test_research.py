"""Offline validation of extracted firmware, inferred wiring, and patch behavior."""
from pathlib import Path
import hashlib
import json
import struct
import sys
import unittest

import pefile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from emulate import APPLICATION, Firmware, GPIO, encoder, display_init
from patch_wheel import APPLICATION_SHA, UPDATER_SHA, patch_application, patch_updater, rcdata, word_sum
from recover_board import recover


class FirmwareResearchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original = APPLICATION.read_bytes()
        cls.updater = (ROOT / "raw/supplier-f75max-firmware.exe").read_bytes()

    def test_extracted_image_identity_and_vendor_checksum(self):
        self.assertEqual(hashlib.sha256(self.updater).hexdigest(), UPDATER_SHA)
        self.assertEqual(hashlib.sha256(self.original).hexdigest(), APPLICATION_SHA)
        self.assertEqual(len(self.original), 262144)
        self.assertEqual(struct.unpack_from("<I", self.original)[0], 0x20002D60)
        self.assertEqual(word_sum(self.original), 0xB9D0)

    def test_matrix_covers_every_vendor_key_and_has_no_shared_drive_sense_pins(self):
        board = recover()
        matrix = board["matrix"]
        self.assertEqual(matrix["vendor_layout_keys"], 80)
        self.assertEqual(matrix["unmatched_vendor_keys"], [])
        self.assertEqual(len(set(matrix["drive_pins"])), 15)
        sense = {p["pin"] for p in matrix["sense_pins"]}
        self.assertEqual(len(sense), 6)
        self.assertFalse(sense & set(matrix["drive_pins"]))

    def test_original_wheel_both_directions_in_both_modes(self):
        for seq, usage, event in [([3, 2, 0, 1, 3], 0xE9, 8), ([3, 1, 0, 2, 3], 0xEA, 9)]:
            self.assertEqual(encoder(seq)[-1]["consumer_usage"], usage)
            self.assertEqual(encoder(seq, menu=True)[-1]["queue_events"], [event, event])

    def test_reversed_wheel_changes_both_media_and_menu_direction(self):
        candidate = patch_application(self.original, reverse=True)
        for seq, usage, event in [([3, 2, 0, 1, 3], 0xEA, 9), ([3, 1, 0, 2, 3], 0xE9, 8)]:
            self.assertEqual(encoder(seq, data=candidate)[-1]["consumer_usage"], usage)
            self.assertEqual(encoder(seq, menu=True, data=candidate)[-1]["queue_events"], [event, event])

    def test_wheel_chatter_does_not_emit_events_before_debounce(self):
        seq = [3, 2, 3, 2, 3, 2, 3]
        self.assertEqual(encoder(seq, stable_calls=1)[-1]["consumer_usage"], 0)
        self.assertEqual(encoder(seq, menu=True, stable_calls=1)[-1]["queue_events"], [])

    def test_configurable_consumer_action_and_debounce(self):
        candidate = patch_application(self.original, debounce_samples=2, positive_usage=0xB5, negative_usage=0xB6)
        self.assertEqual(encoder([3, 2, 0, 1, 3], data=candidate, stable_calls=3)[-1]["consumer_usage"], 0xB5)
        self.assertEqual(encoder([3, 1, 0, 2, 3], data=candidate, stable_calls=3)[-1]["consumer_usage"], 0xB6)

    def test_button_reads_gpio_and_debounces(self):
        fw = Firmware(stubs=[0x107A8])
        fw.word(GPIO[1], 1 << 17)
        fw.run(0x2184)
        fw.word(GPIO[1], 0)
        for _ in range(50):
            fw.run(0x2184)
        self.assertEqual(fw.calls, [])
        fw.run(0x2184)
        self.assertEqual([c["args"][0] for c in fw.calls], [6])
        fw.word(GPIO[1], 1 << 17)
        for _ in range(51):
            fw.run(0x2184)
        self.assertEqual([c["args"][0] for c in fw.calls], [6, 6])

    def test_display_init_has_rgb565_and_known_geometry_offsets(self):
        result = display_init()
        stream = [(c["address"], c["args"][0]) for c in result["calls"]]
        self.assertIn((0x68EC, 0x29), stream)  # Display on
        pixel_format = stream.index((0x68EC, 0x3A))
        self.assertEqual(stream[pixel_format + 1], (0x68E4, 5))  # 16-bit pixels
        self.assertEqual((result["offset_x"], result["offset_y"]), (2, 1))

    def test_vendor_boot_entry_requires_exact_eight_byte_command(self):
        stubs = [0x125C, 0x8D42, 0x8D60, 0x60C6, 0x3ADA, 0x3BD0, 0x14C]
        for command, expected in [(bytes.fromhex("aa42895aff7162cc"), True), (bytes(8), False)]:
            fw = Firmware(stubs=stubs)
            fw.byte(0x2000131A, 2)
            fw.cpu.mem_write(0x2000131C, command)
            fw.run(0x18AA)
            self.assertEqual(any(c["address"] == 0x14C for c in fw.calls), expected)

    def test_repacked_updater_checksums_and_exact_payload_changes(self):
        updater, payload = patch_updater(self.updater, reverse=True, debounce_samples=3)
        pe = pefile.PE(data=updater)
        self.assertTrue(pe.verify_checksum())
        start, length = rcdata(pe, 4000)
        self.assertEqual(updater[start:start + length], payload)
        start, length = rcdata(pe, 4014)
        self.assertEqual(updater[start:start + length].decode("utf-16le"), f"{word_sum(payload):04X}")
        differences = {i for i, (a, b) in enumerate(zip(self.original, payload)) if a != b}
        self.assertEqual(differences, {0x2212, 0x2260, 0x2296, 0x22C6, 0x2300})

    def test_different_firmware_revision_and_invalid_settings_are_rejected(self):
        older = (ROOT / "analysis/firmware/supplier-f75max-v1.08/application.bin").read_bytes()
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            patch_application(older, reverse=True)
        changed = bytearray(self.updater)
        changed[0] ^= 1
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            patch_updater(bytes(changed), reverse=True)
        for value in [0, 256, True]:
            with self.assertRaises(ValueError):
                patch_application(self.original, debounce_samples=value)


if __name__ == "__main__":
    unittest.main()
