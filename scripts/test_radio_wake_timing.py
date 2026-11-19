#!/usr/bin/env python3
"""Execute the linked wake adapter at its 3 ms boundary with modeled UART readiness."""
import hashlib,json,os,struct
from pathlib import Path
from test_keyboard_image import Candidate,SYMBOLS,IMAGE
m=Candidate();m.word(0x40054014,0x60)
m.call('f75_radio_init');m.call('f75_radio_select',2)
def u32(name):return struct.unpack('<I',m.cpu.mem_read(SYMBOLS[name],4))[0]
m.call('f75_radio_task',1000,0)
assert u32('tx_packets')==1 and m.cpu.mem_read(SYMBOLS['waiting'],1)==b'\0','Wake preamble incorrectly waits for an ACK'
for now in (1001,1002):
 m.call('f75_radio_task',now,0);assert u32('tx_packets')==1,'Next packet bypassed 3 ms wake settle'
m.call('f75_radio_task',1003,0)
assert u32('tx_packets')==2 and m.cpu.mem_read(SYMBOLS['waiting'],1)==b'\1','Normal slot command did not follow wake settle'
r=dict(status='passed',candidate_sha256=hashlib.sha256(IMAGE.read_bytes()).hexdigest(),actual_linked_adapter=True,modeled_boundary='UART readiness and timer reads',wake_not_ack_tracked=True,next_packet_blocked_at_1_and_2_ms=True,next_packet_sent_at_3_ms=True,hardware_writes=False)
Path(os.environ['F75_WAKE_RECEIPT']).write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r))
