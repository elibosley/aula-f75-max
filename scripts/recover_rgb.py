#!/usr/bin/env python3
"""Recover LED rows and PWM column routing from the preserved supplier image.
No device access. Peripheral reset completion is modeled; PWM waveforms are not.
"""
import hashlib,json
from pathlib import Path
from unicorn import UC_HOOK_MEM_READ
from emulate import Firmware, APPLICATION
ROOT=Path(__file__).resolve().parents[1]
def recover():
 rows=[]
 for row in range(18):
  f=Firmware();f.byte(0x20000184,row)
  for address in [0x200017ca,0x200018f0,0x20001a16]:f.cpu.mem_write(address,b'\1\0'*126)
  f.run(0x5e7a)
  writes={(w['address'],w['value']) for w in f.writes}
  assert len(writes)==1
  address,mask=writes.pop();rows.append(dict(port=hex(address-0x24),mask=hex(mask)))
 columns=[]
 for col in range(21):
  f=Firmware();f.byte(0x20000184,0)
  f.cpu.mem_write(0x200017ca+col*2,b'\x37\0');f.run(0x5d80)
  hit=[w for w in f.writes if (w['value']&0xffff)==0x37]
  assert len(hit)==int(col<17)
  if hit:columns.append(dict(column=col,register=hex(hit[0]['address'])))
 f=Firmware()
 def reset(cpu,access,address,size,value,context):
  if address in [0x40000000,0x40002000,0x40004000,0x40006000,0x4000a000]:f.word(address,f.word(address)&~2)
 f.cpu.hook_add(UC_HOOK_MEM_READ,reset);f.run(0x8c6e)
 return dict(stock_sha256=hashlib.sha256(APPLICATION.read_bytes()).hexdigest(),hardware_writes=False,
             rows=rows,columns=columns,initialization=f.writes,
             notes=['LED columns share matrix drive pins; disable their PWM mux and all LED rows during every keyboard scan.',
                    'Supplier enables CT16B1 channels 4..10 only, plus all four CT16B0/2 channels: 15 physical columns.',
                    'Supplier row period: 255 ticks at 2MHz; custom application must move its free counter off CT16B0.',
                    'Rows 0..5 use first color array, 6..11 second, 12..17 third. Physical color order needs a visual check.'])
if __name__=='__main__':
 result=recover();p=ROOT/'analysis/wheel-rgb/stock-rgb.json';p.parent.mkdir(exist_ok=True);p.write_text(json.dumps(result,indent=2)+'\n');print(p)
