#!/usr/bin/env python3
"""Exercise the linked read-only asset-flash probe with explicitly modeled SPI1."""
import argparse,hashlib,json,os
from pathlib import Path
from unicorn import UC_HOOK_MEM_READ
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('image',type=Path);parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args();os.environ['F75_IMAGE']=str(args.image.resolve())
from test_keyboard_image import Candidate,IMAGE,SCRATCH

SPI=0x40058000
SAVED=[0x4005e000,0x40042010,0x40044000,0x40044004,SPI,SPI+4,SPI+8,SPI+0x10,SPI+0x20,0xe000e100]

class Probe(Candidate):
 def __init__(self,stuck=False,scan=True):
  self.tx=[];self.stuck=stuck;self.value=0;super().__init__()
  for address,value in [(0x4005e000,0x40000),(0x40042010,0xaaaf),(0x40044000,0x12345),(0x40044004,0x18000),(SPI,0x40700),(SPI+4,3),(SPI+8,7),(SPI+0x10,0),(SPI+0x20,0),(0xe000e100,(1<<19) if scan else 0)]:self.word(address,value)
  self.cpu.hook_add(UC_HOOK_MEM_READ,self.spi_read)
 def spi_read(self,cpu,access,address,size,value,data):
  if address==SPI+0xc:self.word(address,0x14 if self.stuck else 0)
  elif address==SPI+0x1c:self.word(address,self.value)
 def on_write(self,cpu,access,address,size,value,data):
  if address==SPI+0x1c:
   self.tx.append(value&255);n=len(self.tx)
   if self.tx[0]==0x9f:self.value=[0,0xef,0x40,0x18][n-1]
   elif self.tx[0]==3:
    offset=int.from_bytes(bytes(self.tx[1:4]),'big')
    self.value=((offset+n-5)*17+23)&255 if n>=5 else 0
   else:raise AssertionError('Probe sent a non-read SPI command')
  if address==0xe000e180:self.word(0xe000e100,self.word(0xe000e100)&~value)
  elif address==0xe000e100:self.word(address,self.word(address)|value)
  super().on_write(cpu,access,address,size,value,data)

def run():
 cases=0
 for scan in (False,True):
  for operation,address,length in [(0,0,3),(1,0,1),(1,0x123456,18),(1,0xffffee,18)]:
   fw=Probe(scan=scan);saved={a:fw.word(a) for a in SAVED};out=SCRATCH
   fw.cpu.mem_write(out-1,b'\xa5'+bytes(18)+b'\x5a');before=len(fw.writes)
   assert fw.call('f75_storage_probe',operation,address,length,out)==0
   expected=bytes([0xef,0x40,0x18]) if operation==0 else bytes(((address+i)*17+23)&255 for i in range(length))
   assert bytes(fw.cpu.mem_read(out,length))==expected
   assert fw.byte(out-1)==0xa5 and fw.byte(out+18)==0x5a
   assert {a:fw.word(a) for a in SAVED}==saved,'Peripheral state was not restored'
   assert set(w['address'] for w in fw.writes[before:])<={0x4005e000,0x40042010,0x40044004,0x40044024,0x40044028,SPI,SPI+4,SPI+8,SPI+0x10,SPI+0x18,SPI+0x1c,SPI+0x20}
   cases+=1
 for operation,address,length in [(2,0,3),(0,1,3),(0,0,2),(1,0,0),(1,0,19),(1,0xffffff,2),(1,0x1000000,1),(1,0xffffffff,18)]:
  fw=Probe();before=len(fw.writes)
  assert fw.call('f75_storage_probe',operation,address,length,SCRATCH)==1
  assert not fw.tx and len(fw.writes)==before,'Invalid request touched hardware'
 fw=Probe(stuck=True);saved={a:fw.word(a) for a in SAVED}
 assert fw.call('f75_storage_probe',0,0,3,SCRATCH)==2
 assert {a:fw.word(a) for a in SAVED}==saved,'Timeout failed to restore hardware'
 fw=Probe();fw.word(SPI,0x40701);assert fw.call('f75_storage_probe',0,0,3,SCRATCH)==3 and not fw.tx
 for reserved in (False,True):
  fw=Probe();replies=[];fw.callback('raw_hid_send',lambda args:replies.append(bytes(fw.cpu.mem_read(args[0],args[1]))))
  packet=b'F75ztest'+bytes([0,3])+bytes(4)+bytes(17)+bytes([int(reserved)])
  fw.cpu.mem_write(0x20006300,packet);fw.call('raw_hid_receive',0x20006300,32)
  assert len(replies)==1 and replies[0][:8]==b'F75qtest' and replies[0][8]==(1 if reserved else 0)
  assert bool(fw.tx)!=reserved
 return dict(status='passed',candidate_sha256=hashlib.sha256(IMAGE.read_bytes()).hexdigest(),hardware_writes=False,modeled_spi1=True,valid_cases=cases,invalid_cases=8,only_id_and_read_opcodes=True,bounds=True,timeout_and_busy_bounded=True,hardware_state_restored=True,nonce_and_reserved_validation=True,limitations=['Modeled responses do not identify or recover a physical flash chip','This is external asset storage, not a radio firmware dump'])

if __name__=='__main__':
 result=run();args.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
