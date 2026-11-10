#!/usr/bin/env python3
"""Execute settings migration, Save, restart and torn-write recovery in ARM/QEMU."""
import argparse,json,struct,hashlib,tempfile,zlib
from pathlib import Path
from system_emulator import System,HOST
from test_system_emulator import enumerate_usb
A=0x38000;B=0x39000

def run(image):
 image=Path(image)
 def advance(m,ms=100):m.write32(HOST+0x30,0);m.advance(ms);m.pump()
 def request(m,packet):
  m.endpoint_out(3,packet);advance(m);reply=m.endpoint_in(2);assert reply and reply[4:8]==packet[4:8],reply
  return reply
 def save(m):return request(m,b'F75wtestSAVECFG!'+bytes(16))
 def stats(m):return struct.unpack_from('<6I',request(m,b'F75ntest'+bytes(24)),8)
 with System(image) as m:
  enumerate_usb(m);advance(m);assert stats(m)[:3]==(0,0,255)
  m.write(m.symbols['state']+104,bytes([17]));save(m)
  assert stats(m)[:5]==(1,1,0,1,0),stats(m)
  save(m);assert stats(m)[3]==1,'Unchanged Save wore flash again'
  m.write(m.symbols['state']+104,bytes([42]));m.write(m.symbols['f75_custom_config']+12,struct.pack('<H',5));save(m)
  assert stats(m)[:5]==(1,2,1,2,0),stats(m);saved=m.read(A,8192)
  m.write(m.symbols['state']+104,bytes([63]));m.write32(HOST+0x64,m.read32(HOST+0x5c)+10)
  save(m);assert stats(m)[4]==1;torn=m.read(A,8192)
  assert m.read32(HOST+0x60)==0,'Save touched protected code or options'
  assert m.read(0,256)==image.read_bytes()[:256]
  assert m.read(0x3f000,2048)==b'\xff'*2048,'Save overwrote legacy migration pages'
  assert m.read(0x3fffc,4)==bytes.fromhex('5555aaaa')
 with tempfile.TemporaryDirectory() as d:
  for name,pages in [('saved',saved),('torn',torn)]:
   data=bytearray(image.read_bytes());data[A:A+8192]=pages;path=Path(d)/f'{name}.bin';path.write_bytes(data)
   with System(path,symbols_file=image.with_suffix('.elf')) as m:
    enumerate_usb(m);advance(m);assert m.read(m.symbols['state']+104,1)==bytes([42]),name
    assert m.read(m.symbols['f75_custom_config']+12,2)==struct.pack('<H',5),name
    assert stats(m)[:3]==(1,2,1),(name,stats(m))
    if name=='saved':
     crc=m.read(B+4092,4);corrupt=bytes([crc[0]^1])+crc[1:]
     assert m.packet(f'M{B+4092:x},4:'+corrupt.hex())=='OK';assert m.read(B+4092,4)==corrupt
     save(m);assert stats(m)[:5]==(1,3,0,1,0),('Unchanged Save ignored corrupt active CRC',stats(m))
  # A version-4 core record migrates without changing its protected legacy page.
  data=bytearray(image.read_bytes());legacy=bytearray(saved[16:176]);legacy[4]=4;struct.pack_into('<I',legacy,8,7);struct.pack_into('<I',legacy,156,zlib.crc32(legacy[:156]));data[0x3f000:0x3f0a0]=legacy
  path=Path(d)/'legacy.bin';path.write_bytes(data)
  with System(path,symbols_file=image.with_suffix('.elf')) as m:
   enumerate_usb(m);advance(m);assert stats(m)[:3]==(1,7,255)
   assert m.read(m.symbols['state']+104,1)==bytes([17]);save(m);assert stats(m)[:3]==(1,8,0)
   assert m.read(0x3f000,160)==legacy
 return {'status':'passed','candidate_sha256':hashlib.sha256(image.read_bytes()).hexdigest(),'hardware_writes':False,'save_survives_restart':True,'custom_mapping_survives_restart':True,'legacy_migrates_without_overwrite':True,'unchanged_save_does_not_write':True,'torn_new_record_retains_prior':True,'writes_only_reserved_pages':True,'recovery_and_trailer_unchanged':True}
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('image',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args();x=run(a.image);a.output.write_text(json.dumps(x,indent=2)+'\n');print(json.dumps(x))
