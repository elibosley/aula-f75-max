"""Calibration changes only its settings and rejects unsupported or invalid input."""
import copy
import struct
import sys
import unittest
import zlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from keyboard_customize import decode,encode
from test_bluetooth_host import fixture

class BatteryCalibrationTest(unittest.TestCase):
 def document(self,supported=True):
  data=bytearray(fixture());data[129]=int(supported);struct.pack_into('<I',data,156,zlib.crc32(data[:156]));return decode(bytes(data))
 def test_roundtrip_preserves_all_other_preferences(self):
  original=self.document()
  for full in (0,23040,24576,25387,25600):
   for decimals in range(3):
    changed=copy.deepcopy(original);changed['battery'].update(full_soc=full,decimals=decimals)
    data=encode(changed);after=decode(data)
    self.assertEqual(after['battery'],dict(supported=True,full_soc=full,decimals=decimals))
    for key in ('keys','colors','layer_colors','macros','lighting','os','names','power','companion'):
     self.assertEqual(original[key],after[key])
    self.assertEqual(data[164],4)
 def test_invalid_or_unsupported_settings_fail_before_transport(self):
  for full in (-1,1,23039,25601,True):
   doc=self.document();doc['battery']['full_soc']=full
   with self.subTest(full=full),self.assertRaises(ValueError):encode(doc)
  for decimals in (-1,3,1.5,True):
   doc=self.document();doc['battery']['decimals']=decimals
   with self.subTest(decimals=decimals),self.assertRaises(ValueError):encode(doc)
  old=self.document(False);self.assertEqual(decode(encode(old))['battery'],old['battery'])
  old['battery']['decimals']=1
  with self.assertRaisesRegex(ValueError,'Update firmware'):encode(old)
 def test_corrupt_precision_and_reference_are_rejected_on_read(self):
  doc=self.document();doc['battery'].update(full_soc=25600,decimals=2)
  for offset,value in ((160+2526,3),(160+2525,255)):
   data=bytearray(encode(doc));data[offset]=value;struct.pack_into('<I',data,3228,zlib.crc32(data[160:3228]))
   with self.assertRaises(ValueError):decode(bytes(data))
if __name__=='__main__':unittest.main()
