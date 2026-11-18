"""Keep partial results and final settings evidence when recording loses its connection."""

import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import studio_battery_worker as worker
from battery_benchmark import summarize
from studio_battery_sampler import StudioReadError


class StudioWorkerTest(unittest.TestCase):
    def run_worker(self, recording_error=False, final_error=False):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            manifest = dict(thread_id='thread', owner_host_id='local', campaign_id='campaign',
                            attempt_id='attempt', expected_revision='revision', job_id='job',
                            external_attempt=1, firmware_sha256='a' * 64, board_identity='board',
                            runner='runner', probe='probe', source_hashes={})
            (directory / 'manifest.json').write_text(json.dumps(manifest))
            (directory / 'initial-settings.bin').write_bytes(b'complete settings')
            def atomic_bytes(path, data):
                fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(fd, 'wb') as file:
                    file.write(data)
            def atomic_json(path, data):
                atomic_bytes(path, json.dumps(data).encode())
            observer = dict(atomic_json=atomic_json, atomic_bytes=atomic_bytes,
                            proc_identity=lambda pid: {'pid': pid}, proc_matches=lambda record: True)
            sampler = Mock()
            sampler.settings.side_effect = [b'complete settings',
                StudioReadError('measurement_deadline') if final_error else b'complete settings']
            hold = Mock()
            hold.poll.return_value = None
            first = dict(observed_at='2026-11-18T00:00:00+00:00', monotonic_seconds=1000,
                         firmware_sha256='a' * 64, power=dict(gauge_valid=True, usb_configured=False,
                         charging=False, millivolts=4000, raw_soc=12288, percent=50,
                         estimate_percent=50.00, gauge_age_ms=100, uptime_ms=100000, config_crc32=123))
            second = json.loads(json.dumps(first))
            second.update(observed_at='2026-11-18T00:30:00+00:00', monotonic_seconds=2800)
            second['power'].update(raw_soc=12050, percent=49, estimate_percent=49.00, uptime_ms=1900000)
            def record(args):
                args.output.write_text('\n'.join(json.dumps(row) for row in (first, second)) + '\n')
                # This is written to the exact file handed to the real sampler.
                events = create_sampler.call_args.kwargs['event_log']
                events.write('{"event":"retry"}\n')
                events.flush()
                if recording_error:
                    raise StudioReadError('measurement_deadline')
                return summarize([first, second], allow_sampling_gaps=True)
            with patch.object(worker.runpy, 'run_path', return_value=observer), \
                    patch.object(worker, 'StudioSampler', return_value=sampler) as create_sampler, \
                    patch.object(worker.subprocess, 'Popen', return_value=hold), \
                    patch.object(worker.benchmark, 'sample'), \
                    patch.object(worker.benchmark, 'record', side_effect=record), \
                    patch.object(worker.signal, 'signal'), contextlib.redirect_stdout(io.StringIO()):
                code = worker.main(directory)
            result = json.loads((directory / 'result.json').read_text())
            self.assertEqual(result['sleep_assertion_cleanup'], 'complete')
            hold.terminate.assert_called_once()
            self.assertEqual((directory / 'events.jsonl').read_text(), '{"event":"retry"}\n')
            self.assertEqual(result['samples'], 2)
            self.assertEqual(result['summary']['end_estimate_percent'], 49.00)
            self.assertFalse(result['summary']['continuous_sampling_verified'])
            return code, result, (directory / 'final-settings.bin').exists()

    def test_outage_at_deadline_preserves_partial_interval_and_final_snapshot(self):
        code, result, final_exists = self.run_worker(recording_error=True)
        self.assertEqual(code, 1)
        self.assertEqual(result['error_category'], 'measurement_deadline')
        self.assertTrue(result['complete_settings_match'])
        self.assertTrue(final_exists)

    def test_missing_final_settings_remains_unknown(self):
        code, result, final_exists = self.run_worker(recording_error=True, final_error=True)
        self.assertEqual(code, 1)
        self.assertIsNone(result['complete_settings_match'])
        self.assertEqual(result['final_settings_error_category'], 'measurement_deadline')
        self.assertFalse(final_exists)

    def test_success_with_reported_gap_and_full_settings_comparison(self):
        code, result, final_exists = self.run_worker()
        self.assertEqual(code, 0)
        self.assertEqual(result['conclusion'], 'success')
        self.assertTrue(result['complete_settings_match'])
        self.assertTrue(final_exists)
