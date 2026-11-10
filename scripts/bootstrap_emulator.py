#!/usr/bin/env python3
"""Build the pinned QEMU Cortex-M0/F75 machine. Never opens keyboard USB."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
VERSION = '10.1.3'
ARCHIVE_SHA = 'fbaa7a0d7a9a1deb5695b125916746ec28fe0de6275d4454f3e3bbaf8b339b53'
URL = f'https://download.qemu.org/qemu-{VERSION}.tar.xz'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    deps = ROOT / 'builddeps'
    deps.mkdir(exist_ok=True)
    archive = deps / f'qemu-{VERSION}.tar.xz'
    if not archive.exists():
        partial = archive.with_suffix('.partial')
        with urllib.request.urlopen(URL, timeout=60) as response, partial.open('wb') as stream:
            shutil.copyfileobj(response, stream)
        partial.replace(archive)
    if sha(archive) != ARCHIVE_SHA:
        raise SystemExit('Pinned QEMU archive hash mismatch')
    source = deps / f'qemu-{VERSION}'
    if not source.exists():
        with tarfile.open(archive) as stream:
            stream.extractall(deps, filter='data')
    model = ROOT / 'emulator/qemu/f75max.c'
    shutil.copy2(model, source / 'hw/arm/f75max.c')
    for path, extra in [
        ('hw/arm/meson.build', "arm_ss.add(when: 'CONFIG_F75MAX', if_true: files('f75max.c'))"),
        ('hw/arm/Kconfig', 'config F75MAX\n    bool\n    select ARM_V7M'),
    ]:
        target = source / path
        content = target.read_text()
        if extra not in content:
            target.write_text(content + '\n' + extra + '\n')
    (source / 'configs/devices/arm-softmmu/f75max.mak').write_text('CONFIG_F75MAX=y\n')
    build = deps / 'qemu-build'
    build.mkdir(exist_ok=True)
    flags = ['--target-list=arm-softmmu', '--without-default-devices', '--with-devices-arm=f75max',
             '--disable-docs', '--disable-tools', '--disable-guest-agent', '--disable-slirp',
             '--disable-capstone', '--disable-cocoa', '--disable-sdl', '--disable-gtk',
             '--disable-vnc', '--disable-curl']
    env = dict(os.environ, SOURCE_DATE_EPOCH='0', TZ='UTC', LC_ALL='C')
    (ROOT / 'analysis').mkdir(exist_ok=True)
    log = ROOT / 'analysis/qemu-bootstrap.log'
    with log.open('w') as stream:
        subprocess.run([str(source / 'configure'), *flags], cwd=build, env=env,
                       stdout=stream, stderr=subprocess.STDOUT, check=True, timeout=180)
        subprocess.run(['ninja', '-j6', 'qemu-system-arm'], cwd=build, env=env,
                       stdout=stream, stderr=subprocess.STDOUT, check=True, timeout=600)
    binary = build / 'qemu-system-arm'
    receipt = dict(source_url=URL, source_sha256=ARCHIVE_SHA, model_sha256=sha(model),
                   binary_sha256=sha(binary), configure_flags=flags,
                   version=subprocess.check_output([str(binary), '--version'], text=True).splitlines()[0],
                   host=os.uname().sysname + ' ' + os.uname().machine,
                   compiler=subprocess.check_output(['cc', '--version'], text=True).splitlines()[0],
                   glib=subprocess.check_output(['pkg-config', '--modversion', 'glib-2.0'], text=True).strip(),
                   factory_rom_included=False, hardware_writes=False)
    (ROOT / 'analysis/qemu-build.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt, indent=2))


if __name__ == '__main__':
    main()
