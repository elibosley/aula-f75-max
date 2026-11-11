"""Bounded, read-only progress snapshots for foreground settings requests."""
import re
import threading
import time

PHASES = frozenset(('connecting', 'preparing', 'reading', 'sending', 'applying',
                    'saving', 'verifying', 'checking', 'clock'))


class ProgressStore:
    def __init__(self, limit=16, retention=600):
        self.lock = threading.Lock()
        self.records = {}
        self.limit = limit
        self.retention = retention

    def begin(self, identity, action):
        if not isinstance(identity, str) or not re.fullmatch('[0-9a-f]{32}', identity):
            raise ValueError('Invalid progress identifier. Read the keyboard before retrying.')
        now = time.monotonic()
        with self.lock:
            self.records = {key: value for key, value in self.records.items()
                            if value['state'] == 'running' or now - value['updated'] < self.retention}
            if identity in self.records:
                raise ValueError('This operation has already started. Read the keyboard before retrying.')
            while len(self.records) >= self.limit:
                finished = [key for key, value in self.records.items() if value['state'] != 'running']
                if not finished:
                    raise RuntimeError('Keyboard operations are busy.')
                del self.records[finished[0]]
            self.records[identity] = dict(action=action, state='running', phase='connecting',
                                          completed=None, total=None, started=now, updated=now)

    def update(self, identity, phase, completed=None, total=None):
        if phase not in PHASES:
            raise ValueError('Unknown progress phase')
        if completed is not None or total is not None:
            if type(completed) is not int or type(total) is not int or not 0 <= completed <= total or total <= 0:
                raise ValueError('Invalid progress count')
        with self.lock:
            record = self.records[identity]
            if record['state'] == 'running':
                record.update(phase=phase, completed=completed, total=total, updated=time.monotonic())

    def finish(self, identity, success):
        with self.lock:
            self.records[identity].update(state='complete' if success else 'error', updated=time.monotonic())

    def get(self, identity):
        with self.lock:
            record = self.records.get(identity)
            if record is None:
                return None
            if record['state'] != 'running' and time.monotonic() - record['updated'] >= self.retention:
                del self.records[identity]
                return None
            # No settings, text, device identities or exception details are exposed.
            return {key: record[key] for key in ('action', 'state', 'phase', 'completed', 'total')}


PROGRESS = ProgressStore()
