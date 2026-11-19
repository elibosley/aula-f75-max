"""Protect model-specific Fn and diagnostics without opening a device."""
import json
from pathlib import Path
import struct
import sys
import unittest
import zlib

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from keyboard_customize import decode,encode
from test_bluetooth_host import fixture

class S75ProfileTest(unittest.TestCase):
    def test_matrix_matches_official_layout_and_controls_do_not_conflict(self):
        board=json.loads((ROOT/'firmware/targets/s75pro/board-map.json').read_text())
        layout={k['index']:k for k in json.loads((ROOT/'firmware/targets/s75pro/layout.json').read_text())['keys']}
        coordinates=[c for c in board['matrix']['coordinates'] if c.get('vendor_key')]
        self.assertEqual(len(coordinates),80)
        for cell in coordinates:
            key=layout[cell['vendor_key_index']]
            self.assertEqual(int(cell['stock_usage'],16),int(key['usage'],16))
            if key['name']=='Fn':self.assertEqual(cell['scan_index']*6+cell['sense_bit'],65)
        pins=board['rgb']['key_rows']+board['rgb']['side_rows']
        self.assertEqual(len(set(pins)),21)
        self.assertNotIn(board['encoder']['pin_a'],pins)
        self.assertNotIn(board['encoder']['pin_b'],pins)
    def test_codec_reserves_the_board_fn_and_preserves_model(self):
        for model,tag,fn,control in [('f75max',0,71,65),('s75pro',1,65,71)]:
            data=bytearray(fixture());data[130]=tag
            struct.pack_into('<I',data,156,zlib.crc32(data[:156]))
            document=decode(bytes(data));self.assertEqual(document['model'],model)
            document['keys'][0][fn]=4
            with self.assertRaisesRegex(ValueError,'reserved'):encode(document)
            document['keys'][0][fn]=0;document['keys'][0][control]=4
            result=decode(encode(document))
            self.assertEqual(result['model'],model)
            self.assertEqual(result['keys'][0][control],4)

if __name__=='__main__':unittest.main()
