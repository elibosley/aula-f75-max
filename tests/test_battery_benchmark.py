"""Reject powered, stale, discontinuous, or mismatched battery comparisons."""
import copy
import struct
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from battery_benchmark import decode_snapshot, summarize


class BatteryBenchmarkTest(unittest.TestCase):
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


if __name__=='__main__':unittest.main()
