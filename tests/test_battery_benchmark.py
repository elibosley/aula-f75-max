"""Reject powered, stale, discontinuous, or mismatched battery comparisons."""
import copy
import struct
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from battery_benchmark import decode_snapshot, summarize, record
from unittest.mock import patch
import argparse
import contextlib
import io
import json
import tempfile


class BatteryBenchmarkTest(unittest.TestCase):
    def test_fractional_snapshot_preserves_supplier_result_and_reserve(self):
        payload=struct.pack('<BBHHHIIII',2,19|(3<<5),9917,4109,25387,100000,99900,123,7)
        value=decode_snapshot(payload)
        self.assertEqual(value['percent'],100)
        self.assertEqual(value['estimate_percent'],99.17)
        self.assertEqual(value['stage'],'sleep')
        self.assertEqual(value['estimate_basis'],'keyboard full-charge reference')
        unknown=decode_snapshot(struct.pack('<BBHHHIIII',2,2,65535,0,65535,100000,0,123,7))
        self.assertIsNone(unknown['estimate_percent'])
        for estimate in (0,9916,10001,65535):
            with self.subTest(estimate=estimate),self.assertRaises(ValueError):
                decode_snapshot(struct.pack('<BBHHHIIII',2,19,estimate,4109,25387,100000,99900,123,7))

    def payload(self, **changes):
        x=dict(version=1, flags=19, percent=50, stage=2, mv=4000, raw=12288,
               uptime=100000, sampled=99900, config=123, activity=7)
        x.update(changes)
        return struct.pack('<BBBBHHIIII', *x.values())

    def test_schema_and_unknowns(self):
        s=decode_snapshot(self.payload())
        self.assertEqual((s['raw_soc'], s['charging'], s['usb_configured']), (12288, False, False))
        self.assertEqual(s['gauge_age_ms'], 100)
        unknown=decode_snapshot(self.payload(flags=2, percent=255, mv=0, raw=65535))
        self.assertIsNone(unknown['percent'])
        self.assertIsNone(unknown['raw_soc'])
        for change in (dict(version=2), dict(flags=128), dict(stage=4),
                       dict(mv=4600), dict(raw=25601), dict(percent=99),
                       dict(sampled=69999), dict(flags=4)):
            with self.subTest(change=change), self.assertRaises(ValueError):
                decode_snapshot(self.payload(**change))
        self.assertEqual(decode_snapshot(self.payload(uptime=50, sampled=0xfffffff0))['gauge_age_ms'], 66)

    def rows(self):
        a=dict(monotonic_seconds=1000, firmware_sha256='a'*64, power=decode_snapshot(self.payload()))
        b=copy.deepcopy(a);b['monotonic_seconds']=1300;b['power'].update(uptime_ms=400000, percent=49,raw_soc=12050)
        return [a,b]

    def test_interval_is_not_a_full_charge_or_efficiency_claim(self):
        r=summarize(self.rows())
        self.assertEqual(r['raw_soc_drop'],238)
        self.assertFalse(r['full_charge_runtime_measured'])
        self.assertFalse(r['current_draw_measured'])
        self.assertIsNone(r['efficiency_multiplier'])

    def test_invalid_measurements_never_become_results(self):
        for change in (dict(usb_configured=True),dict(charging=True),dict(charging=None),
                       dict(gauge_valid=False),dict(config_crc32=124),dict(uptime_ms=1),
                       dict(gauge_age_ms=30000),dict(raw_soc=25601),dict(percent=5)):
            rows=self.rows();rows[1]['power'].update(change)
            with self.subTest(change=change),self.assertRaises(ValueError):summarize(rows)
        for key,value in [('firmware_sha256','b'*64),('monotonic_seconds',2000),('monotonic_seconds',float('nan')),('monotonic_seconds',True)]:
            rows=self.rows();rows[1][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):summarize(rows)
        with self.assertRaises(ValueError):summarize(self.rows()[:1])

    def test_explicit_gaps_preserve_clock_and_identity_validation(self):
        rows = self.rows()
        rows[1]['monotonic_seconds'] = 2800
        rows[1]['power']['uptime_ms'] = 1900000
        with self.assertRaises(ValueError):
            summarize(rows)
        result = summarize(rows, allow_sampling_gaps=True)
        self.assertEqual(result['elapsed_hours'], 0.5)
        self.assertFalse(result['continuous_sampling_verified'])
        self.assertEqual(result['sampling_gaps'][0]['elapsed_seconds'], 1800)
        for changes in ({'uptime_ms': 1000}, {'config_crc32': 456}, {'charging': True}):
            changed = copy.deepcopy(rows)
            changed[1]['power'].update(changes)
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                summarize(changed, allow_sampling_gaps=True)

    def test_recorder_continues_after_gap_and_returns_summary(self):
        clock = [1000.0]
        powers = [row['power'] for row in self.rows()]
        powers[0]['estimate_percent'] = 50.00
        powers[1].update(uptime_ms=1900000, estimate_percent=49.00)
        def advance(seconds):
            clock[0] += 1800
        with tempfile.TemporaryDirectory() as directory:
            args = argparse.Namespace(transport='bluetooth', cable_unplugged=True,
                                      firmware_sha256='a' * 64, interval=300, duration=1800,
                                      output=Path(directory) / 'samples.jsonl', probe=None,
                                      board='board', allow_sampling_gaps=True)
            with patch('battery_benchmark.time.monotonic', side_effect=lambda: clock[0]), \
                    patch('battery_benchmark.time.sleep', side_effect=advance), \
                    patch('battery_benchmark.sample', side_effect=powers), \
                    contextlib.redirect_stdout(io.StringIO()):
                result = record(args)
            self.assertEqual(result['samples'], 2)
            self.assertEqual(result['end_estimate_percent'], 49.00)
            self.assertFalse(result['continuous_sampling_verified'])
            self.assertEqual(len(args.output.read_text().splitlines()), 2)


if __name__=='__main__':unittest.main()
