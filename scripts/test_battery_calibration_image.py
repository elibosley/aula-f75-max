#!/usr/bin/env python3
"""Verify fractional telemetry and calibration fingerprints in the linked ARM image."""
import argparse,os,struct,zlib,json,hashlib
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('image',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
os.environ['F75_IMAGE']=str(a.image.resolve())
from test_keyboard_image import Candidate,SYMBOLS,SCRATCH,IMAGE
from battery_benchmark import decode_snapshot
m=Candidate();m.initialize_app();custom=SYMBOLS['f75_custom_config']
m.call('f75_custom_encode',custom,SCRATCH);baseline=bytearray(m.cpu.mem_read(SCRATCH,3072))
def calibration(full,decimals):
 data=baseline[:];struct.pack_into('<H',data,2524,full);data[2526]=decimals;struct.pack_into('<I',data,3068,zlib.crc32(data[:3068]));m.cpu.mem_write(SCRATCH,bytes(data));assert m.call('f75_custom_decode',SCRATCH,custom)==1

def raw(args):m.cpu.mem_write(args[0],struct.pack('<H',25387));return 1

def diagnostics(args):m.cpu.mem_write(args[0],struct.pack('<6I',1,100,4109,1,0,99900));return 0

def charging(args):m.byte(args[0],0);return 1
m.callback('f75_battery_raw_soc',raw);m.callback('f75_battery_diagnostics',diagnostics);m.callback('f75_battery_charging',charging)
m.callback('f75_board_usb_active',lambda args:0);m.callback('f75_radio_connected',lambda args:1)
values=[]
for full,decimals in [(0,1),(25600,1),(25600,2)]:
 calibration(full,decimals);m.call('power_snapshot',SCRATCH,100000);payload=bytes(m.cpu.mem_read(SCRATCH,24));assert payload[0]==2
 reading=decode_snapshot(payload);values.append(reading);assert reading['percent']==100 and reading['raw_soc']==25387
 assert reading['estimate_percent']==(100 if full==0 else 99.17)
 m.call('f75_battery_label',SCRATCH+64,round(reading['estimate_percent']*100),decimals)
 label=bytes(m.cpu.mem_read(SCRATCH+64,8)).split(b'\0')[0]
 assert label==(b'100.0%' if full==0 else b'99.2%' if decimals==1 else b'99.17%'),label
assert len({v['config_crc32'] for v in values})==3,'Calibration or precision escaped the log fingerprint'
result=dict(status='passed',candidate_sha256=hashlib.sha256(IMAGE.read_bytes()).hexdigest(),actual_linked_adapter=True,modeled_boundary='Gauge validity/value, charging and live-link observations',wire_payload_bytes=24,legacy_supplier_percent_preserved=True,fractional_estimate=99.17,header_labels=['100.0%','99.2%','99.17%'],calibration_and_precision_in_log_fingerprint=True,hardware_writes=False)
a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
