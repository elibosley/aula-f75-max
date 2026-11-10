#!/usr/bin/env python3
"""Host identity and route isolation checks; no hardware access or key events."""
import tempfile
from pathlib import Path
from host_helper import evidence,enroll,load_bindings

def run():
 board='a'*64;first='b'*64;other='c'*64
 status={'active_slot':1,'radio_connected':True,'auto_mask':31,'transaction':42}
 devices=[{'slot':1,'serial_hash':first}]
 with tempfile.TemporaryDirectory() as d:
  path=Path(d)/'bindings.json';assert evidence(status,board,devices,load_bindings(path),'darwin')[0] is None
  enroll(board,devices,1,path);bindings=load_bindings(path)
  assert evidence(status,board,devices,bindings,'darwin')[0]=={'slot':1,'os':0,'transaction':42}
  assert evidence(status,board,devices,bindings,'win32')[0]=={'slot':1,'os':1,'transaction':42}
  assert evidence(status,other,devices,bindings,'darwin')[0] is None
  assert evidence(status,board,[{'slot':1,'serial_hash':other}],bindings,'darwin')[0] is None
  assert evidence(status,board,devices*2,bindings,'darwin')[0] is None
  assert evidence(status|{'active_slot':2},board,devices,bindings,'darwin')[0] is None
  assert evidence(status|{'radio_connected':False},board,devices,bindings,'darwin')[0] is None
  assert evidence(status|{'auto_mask':29},board,devices,bindings,'darwin')[0] is None
  assert evidence(status|{'active_slot':0},board,devices,bindings,'darwin')[0] is None
  assert evidence(status,board,devices,bindings,'linux')[0] is None
  assert path.stat().st_mode&0o777==0o600
 print('Host helper identity tests passed: enrolled board/device only, manual override, absent/ambiguous/different device, platform and route isolation.')
if __name__=='__main__':run()

# A background helper must not keep sending hints or resyncing a valid clock.
from unittest.mock import patch
import host_helper
class FakeKeyboard:
 def __init__(self,*args,**kwargs):pass
 def __enter__(self):return self
 def __exit__(self,*exc):pass
 status={'helper_protocol':1,'active_slot':1,'radio_connected':True,'auto_mask':31,'transaction':42,'os':[0,1,1,0,1],'evidence_mask':0,'hints_accepted':0,'clock_synced':False}
 reports=0;clocks=0
 def host_status(self):return dict(self.status)
 def report_host_os(self,slot,os,transaction):
  assert slot==1 and os==0 and transaction==42
  self.__class__.reports+=1;self.status['evidence_mask']|=2;self.status['os'][1]=0;self.status['hints_accepted']+=1;return dict(self.status)
 def sync_clock(self,seconds):
  assert 0<=seconds<86400;self.__class__.clocks+=1;self.status['clock_synced']=True;return {'clock_synced':True}
with patch.object(host_helper,'Keyboard',FakeKeyboard),patch.object(host_helper,'metadata',return_value=('board',[{'slot':1,'serial_hash':'device'}])),patch.object(host_helper,'load_bindings',return_value={'boards':{'board':{'1':'device'}}}):
 host_helper.once(sync=False);host_helper.once(sync=False)
 assert FakeKeyboard.reports==FakeKeyboard.clocks==1
 FakeKeyboard.status['auto_mask']=29;FakeKeyboard.status['os'][1]=1
 assert host_helper.once(sync=False)['os_action']=='unchanged' and FakeKeyboard.reports==1
 FakeKeyboard.status['clock_synced']=False;host_helper.once(sync=False,allow_clock=False);assert FakeKeyboard.clocks==1
print('Host helper deduplication and invalid-clock recovery passed.')
schedule=host_helper.ClockSchedule();assert schedule.due(0,1000,0);schedule.observe(0,1000,0,True)
assert not schedule.due(2,1002,0)
assert schedule.due(2,1002,3600),'Timezone change did not resync'
assert schedule.due(2,4602,0),'Sleep or wall-clock jump did not resync'
assert schedule.due(2,900,0),'Backward clock correction did not resync'
schedule.observe(2,1002,0,False);assert schedule.due(3600,4600,0),'Hourly refresh did not resync'
print('Clock schedule: hourly, timezone, sleep and backward/forward wall-clock changes passed.')
import contextlib,io,json
output=io.StringIO()
with patch.object(host_helper,'metadata',side_effect=host_helper.hid.HIDException('simulated disconnect')),patch.object(host_helper,'TransportLock',return_value=contextlib.nullcontext()),patch.object(host_helper.sys,'argv',['host_helper.py','--watch-seconds','1']),contextlib.redirect_stdout(output):
 host_helper.main()
receipts=[json.loads(line) for line in output.getvalue().splitlines()]
assert receipts[0]['service']=='started' and receipts[1]['error']=='simulated disconnect' and receipts[-1]['service']=='stopped'
print('Host helper survives a HID disconnect race and exits its bounded watch cleanly.')
