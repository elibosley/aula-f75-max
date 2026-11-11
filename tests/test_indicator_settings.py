"""Indicator edits round-trip without changing bindings, profiles or older records."""
import struct
import sys
from pathlib import Path
import unittest
import zlib
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from keyboard_customize import decode,encode
from test_bluetooth_host import fixture

class IndicatorSettingsTest(unittest.TestCase):
 def test_legacy_records_stay_byte_identical(self):
  for screen in [None,'#112233']:
   doc=decode(fixture());doc['screen_color']=screen;blob=encode(doc)
   self.assertEqual(encode(decode(blob)),blob)
   self.assertFalse(decode(blob)['indicators']['custom'])
   self.assertTrue(decode(blob)['indicators']['caps'])
 def test_new_colors_and_disabled_options_survive_readback(self):
  baseline=fixture();doc=decode(baseline)
  doc['indicators']={'custom':True,'caps':False,'fn':True,'caps_color':'#ff6600','fn_color':'#2a8dff'}
  actual=encode(doc);roundtrip=decode(actual)
  self.assertEqual(actual[:160],baseline[:160]);self.assertEqual(actual[160:2672],baseline[160:164]+b'\x03'+baseline[165:2672])
  self.assertEqual(roundtrip['indicators'],doc['indicators'])
  self.assertEqual(encode(roundtrip),actual)
  self.assertEqual(roundtrip['keys'],doc['keys'])
 def test_non_boolean_flags_and_invalid_colors_are_rejected(self):
  for name,value in [('caps',1),('fn',None),('custom','yes'),('caps_color','#GGGGGG'),('fn_color','blue')]:
   doc=decode(fixture());doc['indicators'][name]=value
   with self.subTest(name=name),self.assertRaises(ValueError):encode(doc)

if __name__=='__main__':unittest.main()
