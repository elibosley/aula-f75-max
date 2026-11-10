"""Serialize access to the raw-HID response stream across local tools."""
import os
import sys
import time
from pathlib import Path

if os.name == 'nt':
    import msvcrt
else:
    import fcntl

ROOT = Path(__file__).resolve().parents[1]


class TransportLock:
    def __init__(self, timeout=1.0, path=None):
        self.timeout = timeout
        self.paths = [Path(path)] if path else [Path.home() / '.f75-studio' / 'keyboard-config.lock']
        if path is None:
            # Existing checkout-based helpers share this file. A bundled app
            # built into the checkout also participates in that lock.
            roots = Path(sys.executable).resolve().parents if getattr(sys, 'frozen', False) else [ROOT]
            for root in roots:
                legacy = root / '.runtime' / 'keyboard-config.lock'
                if legacy.is_file() and (root / 'scripts' / 'keyboard_customize.py').is_file():
                    self.paths.append(legacy)
                    break
        self.descriptors = []

    def __enter__(self):
        deadline = time.monotonic() + self.timeout
        try:
            for path in self.paths:
                path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                descriptor = os.open(path, os.O_CREAT | os.O_RDWR | getattr(os, 'O_NOFOLLOW', 0), 0o600)
                self.descriptors.append(descriptor)
                while True:
                    try:
                        if os.name == 'nt':
                            msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
                        else:
                            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        break
                    except OSError as error:
                        if time.monotonic() >= deadline:
                            raise RuntimeError('Keyboard transport is busy; wait for the current request') from error
                        time.sleep(.01)
            return self
        except BaseException:
            self.__exit__()
            raise

    def __exit__(self, *exc):
        while self.descriptors:
            os.close(self.descriptors.pop())
