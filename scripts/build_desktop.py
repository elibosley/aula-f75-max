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
    parser.add_argument('--with-bluetooth', action='store_true',
                        help='Include the Mac Bluetooth helper for this checkout’s enrolled keyboard')
    parser.add_argument('--local-bluetooth-preview', action='store_true',
                        help='Build a Mac preview using this checkout’s enrolled keyboard')
    args = parser.parse_args()
    with_bluetooth = args.with_bluetooth or args.local_bluetooth_preview
    if with_bluetooth and sys.platform != 'darwin':
        parser.error('The Bluetooth helper requires macOS.')
    subprocess.run([sys.executable, str(ROOT / 'scripts' / 'build_preview.py')], check=True)
    if sys.platform == 'darwin':
        subprocess.run([sys.executable, str(ROOT / 'scripts' / 'build_native.py')], check=True)
    suffix = '-bluetooth-preview' if args.local_bluetooth_preview else ''
    work = ROOT / '.runtime' / ('desktop-build' + suffix)
    dist = ROOT / 'dist' / ('desktop' + suffix)
    work.mkdir(parents=True, exist_ok=True)
    command = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--windowed', '--name', 'F75 Studio',
               '--workpath', str(work), '--specpath', str(work), '--distpath', str(dist),
               '--add-data', f'{ROOT / "ui"}:ui', '--add-data', f'{BOARD_MAP}:firmware/targets/f75max',
               '--add-data', f'{ROOT / "firmware/targets/s75pro/model.json"}:firmware/targets/s75pro',
               '--add-data', f'{ROOT / "LICENSE"}:licenses',
               '--add-data', f'{ROOT / "THIRD_PARTY_NOTICES.md"}:licenses']
    if sys.platform == 'darwin':
        command.extend(('--add-binary', '/opt/homebrew/lib/libusb-1.0.dylib:.',
                        '--add-data', f'{ROOT / "analysis/libf75.dylib"}:analysis'))
        command.extend(('--osx-bundle-identifier', 'com.f75studio.desktop' + suffix.replace('-', '.', 1)))
    if (ROOT / 'firmware/releases').is_dir():
        command.extend(('--add-data', f'{ROOT / "firmware/releases"}:firmware/releases'))
    command.append(str(ROOT / 'scripts' / 'desktop.py'))
    subprocess.run(command, cwd=ROOT, check=True)
    if with_bluetooth:
        subprocess.run([sys.executable, str(ROOT / 'scripts' / 'build_mac_wireless_probe.py')], check=True)
        app = dist / 'F75 Studio.app'
        helper = ROOT / '.runtime/F75 Wireless Probe.app'
        shutil.copytree(helper, app / 'Contents/Helpers' / helper.name, symlinks=True)
        subprocess.run(['codesign', '--force', '--sign', '-', '--preserve-metadata=identifier,entitlements,flags',
                        str(app)], check=True)
        subprocess.run(['codesign', '--verify', '--deep', '--strict', str(app)], check=True)


if __name__ == '__main__':
    main()
