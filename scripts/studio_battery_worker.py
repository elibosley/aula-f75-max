"""Run one finite Studio battery campaign under its service manager."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import runpy
import signal
import subprocess
import sys
import time

import battery_benchmark as benchmark
from studio_battery_sampler import StudioReadError, StudioSampler


class Interrupted(Exception):
    pass


def interrupted(number, frame):
    raise Interrupted()


def main(directory):
    directory = Path(directory).resolve()
    manifest = json.loads((directory / 'manifest.json').read_text())
    observer = runpy.run_path(manifest['runner'])
    atomic = observer['atomic_json']
    identity = {key: manifest[key] for key in (
        'thread_id', 'owner_host_id', 'campaign_id', 'attempt_id', 'expected_revision',
        'job_id', 'external_attempt', 'firmware_sha256', 'board_identity')}
    os.umask(0o077)
    signal.signal(signal.SIGINT, interrupted)
    signal.signal(signal.SIGTERM, interrupted)
    # Exclusive publication also prevents a restarted LaunchAgent from replaying recording.
    atomic(directory / 'started.json', dict(identity, observed_at_unix=time.time(),
                                           process=observer['proc_identity'](os.getpid())))
    print('measurement_started job=' + manifest['job_id'], flush=True)
    conclusion, category = 'failure', 'startup'
    summary = settings_match = final_error = None
    error_detail = final_error_detail = summary_error = None
    hold = sampler = None
    cleanup = 'not_started'
    events = None
    try:
        for name, digest in manifest['source_hashes'].items():
            if hashlib.sha256(Path(name).read_bytes()).hexdigest() != digest:
                raise StudioReadError('measurement_source_changed')
        fd = os.open(directory / 'events.jsonl', os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        events = os.fdopen(fd, 'w')
        sampler = StudioSampler(manifest, observer['proc_matches'],
                                deadline=time.monotonic() + 300, event_log=events)
        initial = sampler.settings()
        if initial != (directory / 'initial-settings.bin').read_bytes():
            raise StudioReadError('settings_changed_before_start')
        duration = manifest.get('duration_seconds', 86400)
        hold = subprocess.Popen(['/usr/bin/caffeinate', '-i', '-t', str(duration + 900),
                                 '-w', str(os.getpid())],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if hold.poll() is not None:
            raise StudioReadError('temporary_sleep_assertion_failed')
        # Permit the final scheduled read to finish, with a finite 35-second grace.
        sampler.deadline = time.monotonic() + duration + 35
        sampler.log_event('recording_started', duration_seconds=duration)
        benchmark.sample = sampler.sample
        args = argparse.Namespace(transport='bluetooth', cable_unplugged=True,
                                  firmware_sha256=manifest['firmware_sha256'], interval=300,
                                  duration=duration, output=directory / 'samples.jsonl',
                                  probe=Path(manifest['probe']), board=manifest['board_identity'],
                                  allow_sampling_gaps=True, allow_clock_discontinuities=True,
                                  event_callback=sampler.log_event)
        summary = benchmark.record(args)
        conclusion, category = 'success', None
    except Interrupted:
        conclusion, category = 'interrupted', 'worker_signal'
    except Exception as error:
        category = getattr(error, 'reason', type(error).__name__)
        error_detail = str(error)[:2000]
        if sampler is not None:
            sampler.log_event('recording_error', error_category=category, error_message=error_detail)
    finally:
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        if sampler is not None and conclusion != 'interrupted':
            try:
                sampler.deadline = time.monotonic() + 300
                final = sampler.settings()
                observer['atomic_bytes'](directory / 'final-settings.bin', final)
                settings_match = final == (directory / 'initial-settings.bin').read_bytes()
                if not settings_match and conclusion == 'success':
                    conclusion, category = 'failure', 'complete_settings_changed'
            except Exception as error:
                final_error = error.reason if isinstance(error, StudioReadError) else type(error).__name__
                final_error_detail = str(error)[:2000]
                if conclusion == 'success':
                    conclusion, category = 'failure', 'final_settings_unavailable'
        if hold is not None:
            if hold.poll() is None:
                hold.terminate()
            try:
                hold.wait(timeout=5)
            except subprocess.TimeoutExpired:
                hold.kill()
                hold.wait(timeout=5)
            cleanup = 'complete'
        path = directory / 'samples.jsonl'
        rows = []
        if path.exists():
            try:
                for line in path.read_text().splitlines():
                    rows.append(json.loads(line))
            except Exception as error:
                summary_error = dict(category=type(error).__name__, message=str(error)[:2000])
                conclusion, category = 'failure', 'saved_samples_invalid'
        if summary is None and len(rows) >= 2:
            try:
                summary = benchmark.summarize(rows, allow_sampling_gaps=True, allow_clock_discontinuities=True)
                summary['termination'] = 'partial interval after ' + str(category)
            except Exception as error:
                summary_error = dict(category=type(error).__name__, message=str(error)[:2000])
        result = dict(identity, observed_at_unix=time.time(), conclusion=conclusion,
                      error_category=category, error_message=error_detail, summary=summary, samples=len(rows),
                      summary_error=summary_error, final_settings_error_message=final_error_detail,
                      sleep_assertion_cleanup=cleanup, complete_settings_match=settings_match,
                      final_settings_error_category=final_error)
        if sampler is not None:
            sampler.log_event('recording_stopped', conclusion=conclusion, error_category=category,
                              error_message=error_detail, summary_error=summary_error,
                              final_settings_error_message=final_error_detail)
        if events is not None:
            events.close()
        atomic(directory / 'result.json', result)
        print('measurement_terminal conclusion=' + conclusion + ' samples=' + str(len(rows)), flush=True)
    return 0 if conclusion == 'success' else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    raise SystemExit(main(parser.parse_args().directory))
