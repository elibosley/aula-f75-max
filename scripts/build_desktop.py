#!/usr/bin/env python3
"""Bundle F75 Studio on the operating system it will run on."""
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
BOARD_MAP = ROOT / 'firmware' / 'targets' / 'f75max' / 'board-map.json'


def main():
    subprocess.run([sys.executable, str(ROOT / 'scripts' / 'build_preview.py')], check=True)
    work = ROOT / '.runtime' / 'desktop-build'
    work.mkdir(parents=True, exist_ok=True)
    command = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--windowed', '--name', 'F75 Studio',
               '--workpath', str(work), '--specpath', str(work), '--distpath', str(ROOT / 'dist' / 'desktop'),
               '--add-data', f'{ROOT / "ui"}:ui', '--add-data', f'{BOARD_MAP}:firmware/targets/f75max',
               '--add-data', f'{ROOT / "LICENSE"}:licenses',
               '--add-data', f'{ROOT / "THIRD_PARTY_NOTICES.md"}:licenses']
    if sys.platform == 'darwin':
        command.extend(('--osx-bundle-identifier', 'com.f75studio.desktop'))
    command.append(str(ROOT / 'scripts' / 'desktop.py'))
    subprocess.run(command, cwd=ROOT, check=True)


if __name__ == '__main__':
    main()
