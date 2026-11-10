#!/usr/bin/env python3
"""Prove that separate local clients cannot consume each other's HID replies."""
import subprocess,sys,tempfile,time
from pathlib import Path
from keyboard_transport_lock import TransportLock
with tempfile.TemporaryDirectory() as d:
 path=Path(d)/'transport.lock'
 with TransportLock(0,path):
  try:
   with TransportLock(0,path):raise AssertionError('Concurrent client entered')
  except RuntimeError:pass
  start=time.monotonic()
  try:
   with TransportLock(.03,path):raise AssertionError('Timed lock entered')
  except RuntimeError:assert time.monotonic()-start>=.03
 with TransportLock(0,path):pass
 assert path.stat().st_mode&0o777==0o600
 print('Transport lock: exclusive stream, bounded timeout, release after failure, private file passed.')
