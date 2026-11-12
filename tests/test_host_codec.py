"""Offline settings editing must not load a physical USB/HID backend."""
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]


class OfflineCodecTest(unittest.TestCase):
    def test_roundtrip_without_hid_backend(self):
        program = '''
import sys,importlib.abc,struct,zlib
sys.path.insert(0,'scripts')
class NoHid(importlib.abc.MetaPathFinder):
 def find_spec(self,fullname,path=None,target=None):
  if fullname=='hid':raise ImportError('Physical HID backend intentionally unavailable')
sys.meta_path.insert(0,NoHid())
from keyboard_customize import decode,encode,Keyboard
core=bytearray(160);core[:4]=b'F75S';core[4]=5
for i,name in enumerate([b'USB',b'Laptop',b'Tablet',b'Phone',b'Receiver']):
 core[17+i*19:36+i*19]=name.ljust(19,b'\\0')
struct.pack_into('<I',core,156,zlib.crc32(core[:156]))
custom=bytearray(3072);custom[:4]=b'F75C';custom[4]=1
struct.pack_into('<H',custom,6,3072)
struct.pack_into('<I',custom,3068,zlib.crc32(custom[:3068]))
blob=bytes(core+custom);doc=decode(blob)
assert encode(doc)==blob
doc['screen_color']='#ed63d2';doc['lighting']['color']='#42d69b'
changed=decode(encode(doc));assert changed['screen_color']=='#ed63d2' and changed['lighting']['color']=='#42d69b'
assert 'hid' not in sys.modules
try:
 with Keyboard():raise AssertionError('Unavailable physical backend was opened')
except ImportError as error:
 assert str(error)=='Physical HID backend intentionally unavailable'
'''
        result = subprocess.run([sys.executable, '-c', program], cwd=ROOT,
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_arm_clock_check_imports_without_native_preview(self):
        program = """
import sys,ctypes
sys.path.insert(0,'scripts')
load=ctypes.CDLL
def library(name,*args,**kwargs):
 if str(name).endswith('libf75.dylib'):raise AssertionError('ARM check loaded the native preview')
 return load(name,*args,**kwargs)
ctypes.CDLL=library
import test_clock_system
from display_types import View
assert ctypes.sizeof(View)==224
assert 'serve_native' not in sys.modules
"""
        result = subprocess.run([sys.executable, '-c', program], cwd=ROOT,
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
