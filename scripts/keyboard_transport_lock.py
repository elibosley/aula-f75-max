"""Serialize access to the one raw-HID response stream across local tools."""
import fcntl,os,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class TransportLock:
 def __init__(self,timeout=1.0,path=None):self.timeout=timeout;self.path=path or ROOT/'.runtime/keyboard-config.lock';self.fd=None
 def __enter__(self):
  self.path.parent.mkdir(exist_ok=True,mode=0o700)
  self.fd=os.open(self.path,os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600);deadline=time.monotonic()+self.timeout
  try:
   while True:
    try:fcntl.flock(self.fd,fcntl.LOCK_EX|fcntl.LOCK_NB);return self
    except BlockingIOError:
     if time.monotonic()>=deadline:raise RuntimeError('Keyboard transport is busy; wait for the current request')
     time.sleep(.01)
  except BaseException:self.__exit__();raise
 def __exit__(self,*exc):
  if self.fd is not None:os.close(self.fd);self.fd=None
