#!/usr/bin/env python3
"""Bundle F75 Studio on the operating system it will run on."""
import argparse
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
BOARD_MAP = ROOT / 'firmware' / 'targets' / 'f75max' / 'board-map.json'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--local-bluetooth-preview', action='store_true',
                        help='Build a Mac preview using this checkout’s enrolled keyboard')
    args = parser.parse_args()
    if args.local_bluetooth_preview and sys.platform != 'darwin':
        parser.error('The local Bluetooth preview requires macOS.')
    subprocess.run([sys.executable, str(ROOT / 'scripts' / 'build_preview.py')], check=True)
    suffix = '-bluetooth-preview' if args.local_bluetooth_preview else ''
    work = ROOT / '.runtime' / ('desktop-build' + suffix)
    dist = ROOT / 'dist' / ('desktop' + suffix)
    work.mkdir(parents=True, exist_ok=True)
    command = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--windowed', '--name', 'F75 Studio',
               '--workpath', str(work), '--specpath', str(work), '--distpath', str(dist),
               '--add-data', f'{ROOT / "ui"}:ui', '--add-data', f'{BOARD_MAP}:firmware/targets/f75max',
               '--add-data', f'{ROOT / "LICENSE"}:licenses',
               '--add-data', f'{ROOT / "THIRD_PARTY_NOTICES.md"}:licenses']
    if sys.platform == 'darwin':
        command.extend(('--osx-bundle-identifier', 'com.f75studio.desktop' + suffix.replace('-', '.', 1)))
    command.append(str(ROOT / 'scripts' / 'desktop.py'))
    subprocess.run(command, cwd=ROOT, check=True)
    if args.local_bluetooth_preview:
        subprocess.run([sys.executable, str(ROOT / 'scripts' / 'build_mac_wireless_probe.py')], check=True)
        app = dist / 'F75 Studio.app'
        helper = ROOT / '.runtime/F75 Wireless Probe.app'
        shutil.copytree(helper, app / 'Contents/Helpers' / helper.name, symlinks=True)
        subprocess.run(['codesign', '--force', '--sign', '-', '--preserve-metadata=identifier,entitlements,flags',
                        str(app)], check=True)
        subprocess.run(['codesign', '--verify', '--deep', '--strict', str(app)], check=True)


if __name__ == '__main__':
    main()
