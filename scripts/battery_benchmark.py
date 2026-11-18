#!/usr/bin/env python3
"""Read fixed power telemetry, record a finite discharge run, or summarize it.

This never changes settings, flashes firmware, injects keys, or infers current
from SOC. A service manager must own long runs; this is not a detached waiter.
"""
import argparse
import datetime
import fcntl
import json
import math
import os
from pathlib import Path
import struct
import time


def decode_snapshot(payload):
    if len(payload) != 24:
        raise ValueError('Power snapshot must contain 24 bytes')
    version, flags, percent, stage, mv, raw, uptime, sampled, config, activity = struct.unpack('<BBBBHHIIII', payload)
    estimate = None
    if version == 2:
        estimate = struct.unpack_from('<H', payload, 2)[0]
        stage = (flags >> 5) & 3
        if flags & 128:
            raise ValueError('Unknown power snapshot flags')
        flags &= 31
        percent = min(100, raw * 100 // 24576)
    elif version != 1:
        raise ValueError('Unknown power snapshot schema')
    if flags & ~31 or stage > 3:
        raise ValueError('Unknown power snapshot schema, flags, or stage')
    valid = bool(flags & 1)
    age = (uptime - sampled) & 0xffffffff
    if valid and (not 2800 <= mv <= 4500 or raw > 25600 or
                  percent != min(100, raw * 100 // 24576) or age >= 30000 or
                  (estimate is not None and not min(10000,(raw*10000+12800)//25600) <= estimate <= min(10000,(raw*10000+11520)//23040))):
        raise ValueError('Invalid or stale gauge measurement')
    if not valid and ((version == 1 and percent != 255) or (version == 2 and estimate != 65535) or mv != 0 or raw != 65535):
        raise ValueError('Unavailable gauge must preserve unknown values')
    if flags & 4 and not flags & 2:
        raise ValueError('Charging cannot be true without a known charging input')
    if valid and estimate is None:
        estimate = min(10000, (raw * 10000 + 12288) // 24576)
    return dict(gauge_valid=valid, percent=percent if valid else None,
                estimate_percent=estimate / 100 if valid else None,
                estimate_basis='keyboard full-charge reference' if version == 2 else 'supplier scale',
                millivolts=mv if valid else None, raw_soc=raw if valid else None,
                charging=bool(flags & 4) if flags & 2 else None,
                usb_configured=bool(flags & 8), radio_connected=bool(flags & 16),
                stage=['active', 'dim', 'off', 'sleep'][stage], uptime_ms=uptime,
                gauge_age_ms=age if valid else None, config_crc32=config,
                activity_epoch=activity)


def sample(transport, probe=None, board=None):
    if transport == 'usb':
        from keyboard_customize import Keyboard
        device = Keyboard(); device.expected_board = board
        with device:
            reply = device.raw_request(b'F75b')
        if len(reply) != 32 or reply[:4] != b'F75c':
            raise ValueError('Power snapshot reply did not verify')
        data = reply[8:]
    else:
        from keyboard_bluetooth import BluetoothKeyboard
        device = BluetoothKeyboard(probe, fast=True); device.expected_board = board
        with device:
            data = device.power_snapshot()
    return decode_snapshot(data)


def validate_discharge(rows, max_gap):
    if len(rows) < 2:
        raise ValueError('At least two battery-only samples are required')
    first = rows[0]
    for previous, row in zip(rows, rows[1:]):
        for value in (previous, row):
            p = value['power']; stamp = value['monotonic_seconds']
            if isinstance(stamp, bool) or not isinstance(stamp, (int, float)) or not math.isfinite(stamp):
                raise ValueError('Invalid monotonic timestamp')
            if p['gauge_valid'] is not True or p['usb_configured'] is not False or p['charging'] is not False:
                raise ValueError('Discharge samples must be fresh, known, and externally unpowered')
            for key, low, high in (('millivolts', 2800, 4500), ('raw_soc', 0, 25600),
                                   ('percent', 0, 100), ('gauge_age_ms', 0, 29999),
                                   ('uptime_ms', 0, 0xffffffff), ('config_crc32', 0, 0xffffffff)):
                if type(p[key]) is not int or not low <= p[key] <= high:
                    raise ValueError('Invalid gauge field: ' + key)
            if p['percent'] != min(100, p['raw_soc'] * 100 // 24576):
                raise ValueError('Gauge percentage and raw SOC disagree')
            if value['firmware_sha256'] != first['firmware_sha256'] or value['power']['config_crc32'] != first['power']['config_crc32']:
                raise ValueError('Firmware or configuration changed during the run')
        elapsed = row['monotonic_seconds'] - previous['monotonic_seconds']
        if not math.isfinite(elapsed) or elapsed <= 0 or (max_gap is not None and elapsed > max_gap):
            raise ValueError('Missing samples, clock discontinuity, or host sleep invalidated continuous timing')
        device_elapsed = (row['power']['uptime_ms'] - previous['power']['uptime_ms']) & 0xffffffff
        if abs(device_elapsed / 1000 - elapsed) > 10:
            raise ValueError('Keyboard restarted or its clock disagrees with host elapsed time')
    return rows[-1]['monotonic_seconds'] - first['monotonic_seconds']


def summarize(rows, max_gap=660, allow_sampling_gaps=False):
    elapsed = validate_discharge(rows, None if allow_sampling_gaps else max_gap)
    gaps = [dict(after=previous.get('observed_at'), before=row.get('observed_at'),
                 elapsed_seconds=row['monotonic_seconds'] - previous['monotonic_seconds'])
            for previous, row in zip(rows, rows[1:])
            if row['monotonic_seconds'] - previous['monotonic_seconds'] > max_gap]
    start, end = rows[0]['power'], rows[-1]['power']
    return dict(status='measured_interval', samples=len(rows), elapsed_hours=elapsed / 3600,
                sampling_gaps=gaps, continuous_sampling_verified=not gaps,
                start_estimate_percent=start.get('estimate_percent'),
                end_estimate_percent=end.get('estimate_percent'),
                start_percent=start['percent'], end_percent=end['percent'],
                raw_soc_drop=start['raw_soc'] - end['raw_soc'],
                start_millivolts=start['millivolts'], end_millivolts=end['millivolts'],
                full_charge_runtime_measured=False, efficiency_multiplier=None,
                current_draw_measured=False, measurement='supplier gauge estimate, not energy or current')


def record(args):
    if args.transport != 'bluetooth' or not args.cable_unplugged:
        raise ValueError('A discharge run requires Bluetooth and an explicit physically unplugged cable')
    if len(args.firmware_sha256 or '') != 64 or any(c not in '0123456789abcdef' for c in args.firmware_sha256):
        raise ValueError('Provide the exact installed firmware SHA-256')
    if not 300 <= args.interval <= 3600 or not args.interval <= args.duration <= 31 * 86400:
        raise ValueError('Use a 300..3600 second interval and a finite duration of at most 31 days')
    # Exclusive, private, append-only output. Never reuse or overwrite a run.
    descriptor = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    rows = []
    with os.fdopen(descriptor, 'w') as output:
        fcntl.flock(output, fcntl.LOCK_EX | fcntl.LOCK_NB)
        started = time.monotonic()
        while True:
            power = sample('bluetooth', args.probe, args.board)
            row = dict(observed_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                       monotonic_seconds=time.monotonic(), firmware_sha256=args.firmware_sha256,
                       firmware_identity='operator-supplied installed-image identity; not device attestation',
                       power=power)
            # A powered/unknown sample cannot become a battery-runtime result.
            if not power['gauge_valid'] or power['usb_configured'] or power['charging'] is not False:
                raise ValueError('Cable power, unknown charge state, or unavailable gauge invalidates discharge recording')
            rows.append(row)
            if len(rows) > 1:
                validate_discharge(rows[-2:], None if getattr(args, 'allow_sampling_gaps', False) else args.interval * 2 + 60)
                if power['config_crc32'] != rows[0]['power']['config_crc32']:
                    raise ValueError('Configuration changed during discharge recording')
            output.write(json.dumps(row, separators=(',', ':')) + '\n'); output.flush(); os.fsync(output.fileno())
            if power.get('estimate_percent', power['percent']) <= 5 or time.monotonic() - started >= args.duration:
                break
            time.sleep(max(0, min(args.interval, args.duration - (time.monotonic() - started))))
    result = summarize(rows, args.interval * 2 + 60, getattr(args, 'allow_sampling_gaps', False))
    result['termination'] = '5-percent reserve' if rows[-1]['power'].get('estimate_percent', rows[-1]['power']['percent']) <= 5 else 'finite-duration limit'
    print(json.dumps(result, indent=2))
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    action = p.add_mutually_exclusive_group(required=True)
    action.add_argument('--sample', action='store_true')
    action.add_argument('--record', action='store_true')
    action.add_argument('--summarize', type=Path)
    p.add_argument('--transport', choices=['usb', 'bluetooth'], default='bluetooth')
    p.add_argument('--probe', type=Path)
    p.add_argument('--board')
    p.add_argument('--firmware-sha256')
    p.add_argument('--cable-unplugged', action='store_true')
    p.add_argument('--interval', type=int, default=300)
    p.add_argument('--duration', type=int, default=86400)
    p.add_argument('--output', type=Path)
    p.add_argument('--allow-sampling-gaps', action='store_true',
                   help='Keep explicitly reported Bluetooth sample gaps in the interval')
    a = p.parse_args()
    if a.summarize:
        print(json.dumps(summarize([json.loads(line) for line in a.summarize.read_text().splitlines()], a.interval * 2 + 60, a.allow_sampling_gaps), indent=2))
    elif a.record:
        if not a.output or not a.probe or not a.board:
            p.error('--record requires --output, --probe, and the enrolled --board identity')
        record(a)
    else:
        if a.transport == 'bluetooth' and not a.probe:
            p.error('Bluetooth requires the already-enrolled --probe')
        print(json.dumps(sample(a.transport, a.probe, a.board), indent=2))


if __name__ == '__main__':
    main()
