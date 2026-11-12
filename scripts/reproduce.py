#!/usr/bin/env python3
"""Clean-build both profiles twice, compare artifacts, and run ARM system tests.

This command never calls probe, flash, restore, or diagnostics hardware tools.
"""
import argparse
import fcntl
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import uuid

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(command, log, env=None, timeout=300):
    try:
        with log.open('w') as stream:
            subprocess.run(command, cwd=ROOT, env=env, stdout=stream, stderr=subprocess.STDOUT,
                           check=True, timeout=timeout)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        print(f'Failed command log: {log.relative_to(ROOT)}', file=sys.stderr, flush=True)
        print('\n'.join(log.read_text(errors='replace').splitlines()[-60:]), file=sys.stderr, flush=True)
        raise


def verify_sources():
    """Reject changed archive-owned sources, except exact recorded local patches."""
    manifest = json.loads((ROOT / 'firmware/targets/f75max/dependencies.json').read_text())
    patches = {
        'os/common/ext/SONiX/SN32F2xx/system_SN32F290.c': 'f57a00d37cd3c22cba22a6ae23db751e147581ee3addfe998a918dfa99ea618f',
        'os/hal/ports/SN32/LLD/SN32F2xx/SPI/hal_spi_v2_lld.c': json.loads((ROOT / 'firmware/targets/f75max/patches/spi-master-completion.json').read_text())['after_sha256'],
    }
    for patch in json.loads((ROOT / 'firmware/targets/f75max/patches/systick-timer4.json').read_text()):
        relative = Path(patch['source']).relative_to('builddeps/chibios-contrib')
        patches[str(relative)] = patch['after_sha256']
    result = []
    for item in manifest['sources']:
        archive = ROOT / 'builddeps' / (item['name'] + '.tar.gz')
        assert sha(archive) == item['archive_sha256'], f'Archive changed: {archive}'
        checked = 0
        with tarfile.open(archive) as package:
            for member in package:
                if not member.isfile():
                    continue
                relative = Path(*Path(member.name).parts[1:])
                path = ROOT / 'builddeps' / item['name'] / relative
                original = hashlib.sha256(package.extractfile(member).read()).hexdigest()
                allowed = {original}
                if item['name'] == 'chibios-contrib' and str(relative) in patches:
                    allowed.add(patches[str(relative)])
                assert path.is_file() and sha(path) in allowed, f'Unrecorded dependency mutation: {path}'
                checked += 1
        result.append(dict(name=item['name'], revision=item['revision'], archive_sha256=item['archive_sha256'], files_verified=checked))
    toolchain = ROOT / 'builddeps/arm-toolchain.tar.gz'
    assert sha(toolchain) == manifest['toolchain']['sha256']
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bootstrap', action='store_true', help='Fetch pinned sources/tools and build QEMU first')
    parser.add_argument('--source-only', action='store_true', help='Run public build checks without private research captures')
    args = parser.parse_args()
    lock = ROOT / '.runtime/reproduce.lock'
    lock.parent.mkdir(exist_ok=True, mode=0o700)
    campaign_lock = os.open(lock, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(campaign_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise SystemExit('A reproduction run is already active; no duplicate build was started')
    attempt = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8]
    out = ROOT / 'analysis/repro/runs' / attempt
    out.mkdir(parents=True)
    receipt = dict(status='running', attempt=attempt, hardware_writes=False,
                   python=sys.version, platform=os.uname().sysname + ' ' + os.uname().machine,
                   profiles={}, scope='Two complete clean builds per profile, same host and source directory')
    path = out / 'receipt.json'
    try:
        if args.bootstrap:
            run([sys.executable, 'scripts/bootstrap_keyboard.py'], out / 'bootstrap-keyboard.log')
            run([sys.executable, 'scripts/bootstrap_emulator.py'], out / 'bootstrap-emulator.log', timeout=900)
        receipt['verified_dependencies'] = verify_sources()
        receipt['python_lock_sha256'] = sha(ROOT / 'requirements-build.lock')
        receipt['build_script_sha256'] = sha(ROOT / 'scripts/build_keyboard.py')
        for profile in ['usb_only', 'full_ui']:
            print(f'Building {profile} twice from clean objects...', flush=True)
            for attempt_name in ['a', 'b']:
                dest = out / profile / attempt_name
                dest.mkdir(parents=True)
                command = [sys.executable, 'scripts/build_keyboard.py', '--clean', '--output-dir', str(dest)]
                if profile == 'usb_only': command.append('--usb-only')
                run(command, dest / 'driver.log')
            a, b = out / profile / 'a', out / profile / 'b'
            compared = {}
            for suffix in ['bin', 'elf']:
                filename = 'f75max-wired-test.' + suffix
                assert sha(a / filename) == sha(b / filename), f'{profile} {suffix} is not reproducible'
                compared[suffix] = sha(b / filename)
            assert sha(a / 'build-inputs.json') == sha(b / 'build-inputs.json'), 'Build inputs changed between clean builds'
            env = dict(os.environ, F75_IMAGE=str(b / 'f75max-wired-test.bin'), F75_TEST_RECEIPT=str(b / 'adapter-tests.json'))
            run([sys.executable, 'scripts/test_keyboard_image.py'], b / 'adapter-tests.log', env=env)
            run([sys.executable, 'scripts/test_system_emulator.py', str(b / 'f75max-wired-test.bin'),
                 '--output', str(b / 'system-tests.json')]+(['--source-only'] if args.source_only else []), b / 'system-tests.log')
            result = json.loads((b / 'system-tests.json').read_text())
            assert result['status'] == 'passed' and result['candidate_sha256'] == compared['bin']
            focused = {}
            if profile == 'full_ui':
                scripts = {
                    'settings': 'test_settings_system.py', 'os': 'test_os_system.py',
                    'host-os': 'test_host_os_system.py', 'radio': 'test_radio_system.py',
                    'pairing': 'test_pairing_system.py', 'menu': 'test_menu_system.py',
                    'switch-failure': 'test_switch_failure_system.py',
                    'custom': 'test_custom_system.py', 'battery': 'test_battery_image.py',
                    'power-scroll': 'test_power_scroll.py', 'idle-power': 'test_idle_power.py',
                    'profiles': 'test_profiles_system.py', 'clock': 'test_clock_system.py',
                    'storage': 'test_storage_probe.py',
                    'companions': 'test_companion_system.py',
                    'animation-speed': 'test_animation_system.py',
                    'route-memory': 'test_route_system.py',
                    'host-display': 'test_host_display_system.py',
                    'info-signs': 'test_info_signs_system.py',
                    'indicators': 'test_indicators_system.py',
                    'bluetooth-settings': 'test_bluetooth_settings_system.py',
                    'fast-bluetooth': 'test_fast_bluetooth_system.py',
                    'bluetooth-clock': 'test_bluetooth_clock_system.py',
                    'bluetooth-consumer': 'test_bluetooth_consumer_system.py',
                }
                for name, script in scripts.items():
                    print(f'Checking {name} on the exact full_ui image...', flush=True)
                    target = b / (name + '-tests.json')
                    # The exhaustive UART snapshot test takes ~200s on the
                    # owner Mac; hosted emulation can exceed the default 300s.
                    # Keep its assertions and finite deadline unchanged in scope.
                    timeout = 600 if name == 'bluetooth-settings' else 300
                    run([sys.executable, 'scripts/' + script, str(b / 'f75max-wired-test.bin'),
                         '--output', str(target)], b / (name + '-tests.log'), timeout=timeout)
                    check = json.loads(target.read_text())
                    assert check['status'] == 'passed' and check['candidate_sha256'] == compared['bin']
                    assert sha(b / 'f75max-wired-test.bin') == compared['bin'], 'Test modified the input image'
                    focused[name] = str(target.relative_to(ROOT))
            receipt['profiles'][profile] = dict(status='passed', identical_clean_builds=2, sha256=compared,
                                               build_inputs_sha256=sha(b / 'build-inputs.json'),
                                               adapter_receipt=str((b / 'adapter-tests.json').relative_to(ROOT)),
                                               system_receipt=str((b / 'system-tests.json').relative_to(ROOT)),
                                               focused_receipts=focused)
            print(f'{profile}: reproducible; ARM adapter and full-system checks passed.', flush=True)
        if not args.source_only:run([sys.executable, '-m', 'unittest', 'discover', '-s', 'tests'], out / 'research-tests.log')
        receipt['private_research_checks'] = 'not_run' if args.source_only else 'passed'
        receipt['status'] = 'passed'
        full = out / 'full_ui/b/f75max-wired-test.bin'
        # Verification creates an uninstalled artifact. Keep the installed
        # emulator/deployment pointer separate from this reproduction result.
        receipt['emulator_image'] = dict(image=str(full.relative_to(ROOT)), sha256=sha(full),
                                         profile='full_ui', hardware_tested=False)
    except Exception as error:
        receipt['status'] = 'failed'
        receipt['error'] = f'{type(error).__name__}: {error}'
        raise
    finally:
        path.write_text(json.dumps(receipt, indent=2) + '\n')
        latest = ROOT / 'analysis/repro/latest.json'
        temporary = latest.with_suffix('.tmp')
        temporary.write_text(json.dumps(dict(status=receipt['status'], receipt=str(path.relative_to(ROOT))), indent=2) + '\n')
        temporary.replace(latest)
    print(f'Passed. Receipt: {path}')


if __name__ == '__main__':
    main()
