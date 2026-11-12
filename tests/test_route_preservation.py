"""Route preferences survive upgrades without saving unrelated RAM settings."""
import hashlib,json,struct,sys,tempfile,unittest,zlib
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import flash_keyboard as flash
class RoutePreservationTest(unittest.TestCase):
 def fixture(self,root,journal=None):
  source=bytearray(b'\xff'*262144)
  if journal is None:source[0x3e800:0x3f000]=bytes(2048)
  digest=hashlib.sha256(source).hexdigest();folder=root/'analysis/candidates'/digest;folder.mkdir(parents=True);(folder/'f75max-wired-test.bin').write_bytes(source)
  current=bytearray(source)
  backup=dict(source_image_sha256=digest,records_hex=['ff'*160]*2,custom_regions=[],last_connected_bt=2)
  if journal is not None:
   backup['route_regions']=[dict(address=0x3e800,hex=journal.hex())];current[0x3e800:0x3f000]=journal
  checksum=flash.checksum(current);backup['source_checksum']=f'{checksum:04x}'
  return backup,checksum
 def test_first_upgrade_seeds_only_confirmed_bluetooth_slot(self):
  with tempfile.TemporaryDirectory() as directory,patch.object(flash,'ROOT',Path(directory)):
   backup,checksum=self.fixture(Path(directory));image=b'\xff'*262144
   merged=flash.preserve_settings(image,backup,checksum,route_reserved=True)
   entry=merged[0x3e800:0x3e810];self.assertEqual(struct.unpack('<4sII',entry[:12]),(b'F75R',1,2));self.assertEqual(struct.unpack('<I',entry[12:])[0],zlib.crc32(entry[:12]))
   self.assertEqual(merged[:0x3e800],image[:0x3e800]);self.assertEqual(merged[0x3e810:],image[0x3e810:])
   self.assertEqual(flash.preserve_settings(image,backup,checksum),image)
   backup['last_connected_bt']=True
   with self.assertRaises(ValueError):flash.preserve_settings(image,backup,checksum,route_reserved=True)
 def test_existing_journal_is_preserved_byte_exact(self):
  entry=struct.pack('<4sII',b'F75R',12,3);entry+=struct.pack('<I',zlib.crc32(entry));journal=entry+b'\xff'*(2048-16)
  with tempfile.TemporaryDirectory() as directory,patch.object(flash,'ROOT',Path(directory)):
   backup,checksum=self.fixture(Path(directory),journal)
   image=b'\xff'*262144;merged=flash.preserve_settings(image,backup,checksum,route_reserved=True)
   self.assertEqual(merged[0x3e800:0x3f000],journal)
   with self.assertRaises(ValueError):flash.preserve_settings(image,backup,checksum)
   backup['route_regions'][0]['address']=0x3f800
   with self.assertRaises(ValueError):flash.preserve_settings(image,backup,checksum,route_reserved=True)
if __name__=='__main__':unittest.main()
