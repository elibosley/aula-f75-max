#!/usr/bin/env python3
"""Framing tests for buffered QEMU sockets; no QEMU/device/network access."""
from system_emulator import System
class Socket:
    def __init__(self,chunks):self.chunks=list(chunks);self.sent=[]
    def recv(self,size):return self.chunks.pop(0) if self.chunks else b''
    def sendall(self,data):self.sent.append(data)
def packet(text):
    b=text.encode();return b'$'+b+b'#'+f'{sum(b)&255:02x}'.encode()
def machine(gdb=(),test=()):
    s=System.__new__(System);s.gdb=Socket(gdb);s.test=Socket(test);s._gdb_buffer=bytearray();s._qtest_buffer=bytearray();return s
for cuts in [1,2,7,4096]:
    data=b'+'+packet('T05')+packet('OK')
    m=machine([data[n:n+cuts] for n in range(0,len(data),cuts)])
    assert m.response()=='T05' and m.response()=='OK' and m.gdb.sent==[b'+',b'+']
    data=b'OK 0x1234\nOK 0xabcd\n'
    m=machine(test=[data[n:n+cuts] for n in range(0,len(data),cuts)])
    assert m.command('readl 0x10')==['0x1234'] and m.command('readl 0x20')==['0xabcd']
for action in [lambda:machine().response(),lambda:machine().command('readl 0x10')]:
    try:action();assert False
    except RuntimeError:pass
try:machine([b'$OK#00']).response();assert False
except AssertionError:pass
print('Buffered GDB/qtest framing passed: fragmented/coalesced packets, checksum, EOF.')
