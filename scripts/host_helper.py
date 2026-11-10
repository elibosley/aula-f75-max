#!/usr/bin/env python3
"""Optional cabled host helper. Enumerates device metadata; never reads keys.

Bluetooth host evidence is accepted only for an explicitly enrolled serial
identity belonging to this USB keyboard. No startup service is installed here.
"""
import argparse,contextlib,datetime,hashlib,json,os,signal,sys,tempfile,threading,time
from pathlib import Path
import hid
from keyboard_customize import Keyboard,ROOT
from keyboard_transport_lock import TransportLock
BINDINGS=ROOT/'.runtime/host-bindings.json'
class ClockSchedule:
 def __init__(self):self.next=0;self.previous=None
 def due(self,monotonic,wall,offset):
  if monotonic>=self.next:return True
  if self.previous:
   prior_mono,prior_wall,prior_offset=self.previous
   return offset!=prior_offset or abs((wall-prior_wall)-(monotonic-prior_mono))>2
  return True
 def observe(self,monotonic,wall,offset,synced):
  self.previous=(monotonic,wall,offset)
  if synced:self.next=monotonic+3600

def identity(serial):
 if not isinstance(serial,str) or not serial:raise ValueError('Device has no stable serial identity; use a manual layout')
 return hashlib.sha256(serial.encode()).hexdigest()
def metadata():
 devices=hid.enumerate(0xfeed,0xf750)+hid.enumerate(0x05ac,0x024f);usb=[d for d in devices if (d['vendor_id'],d['product_id'],d['usage_page'])==(0xfeed,0xf750,0xff60)]
 if len(usb)!=1:raise RuntimeError('Exactly one connected USB keyboard is required')
 wireless=[]
 for d in devices:
  if (d['vendor_id'],d['product_id'],d['usage_page'],d['usage'])!=(0x05ac,0x024f,1,6):continue
  product=d.get('product_string','');bus=d.get('bus_type')
  if bus==hid.BusType.BLUETOOTH and product in ('AULA F75Max-1','AULA F75Max-2','AULA F75Max-3'):slot=int(product[-1])
  elif bus==hid.BusType.USB and product=='2.4G Dongle':slot=4
  else:continue
  wireless.append({'slot':slot,'serial_hash':identity(d.get('serial_number'))})
 return identity(usb[0].get('serial_number')),wireless

def load_bindings(path=BINDINGS):
 if not path.exists():return {'version':1,'boards':{}}
 if path.is_symlink():raise ValueError('Binding file must not be a symlink')
 result=json.loads(path.read_text())
 if result.get('version')!=1 or not isinstance(result.get('boards'),dict):raise ValueError('Invalid host bindings file')
 return result

def enroll(board,devices,slot,path=BINDINGS):
 matches=[d for d in devices if d['slot']==slot]
 if len(matches)!=1:raise ValueError('Exactly one local device must match this wireless slot')
 data=load_bindings(path);data['boards'].setdefault(board,{})[str(slot)]=matches[0]['serial_hash']
 path.parent.mkdir(exist_ok=True,mode=0o700)
 fd,temp=tempfile.mkstemp(prefix='.host-bindings-',dir=path.parent)
 try:
  with os.fdopen(fd,'w') as stream:json.dump(data,stream,indent=2);stream.write('\n');stream.flush();os.fsync(stream.fileno())
  os.replace(temp,path)
 finally:
  with contextlib.suppress(FileNotFoundError):os.unlink(temp)
 return {'enrolled_slot':slot,'board_identity_stored_as_hash':True,'wireless_identity_stored_as_hash':True}

def evidence(status,board,devices,bindings,platform=sys.platform):
 if platform=='darwin':host_os=0
 elif platform=='win32':host_os=1
 else:return None,'Only Mac and Windows host detection is supported'
 slot=status['active_slot']
 if slot==0:return None,'USB uses keyboard-side host detection'
 if not status['radio_connected']:return None,'Wireless link is not connected'
 if not status['auto_mask']&(1<<slot):return None,'Manual layout override is active'
 expected=bindings['boards'].get(board,{}).get(str(slot))
 if not expected:return None,'Wireless device has not been enrolled for this USB keyboard'
 matches=[d for d in devices if d['slot']==slot]
 if len(matches)!=1 or matches[0]['serial_hash']!=expected:return None,'The enrolled wireless device is not uniquely connected to this host'
 return {'slot':slot,'os':host_os,'transaction':status['transaction']},None

def once(sync=True,dry_run=False,save_enrollment=None,allow_clock=True):
 board,devices=metadata()
 with Keyboard(lock_timeout=0) as keyboard:
  status=keyboard.host_status()
  if save_enrollment is not None:
   if status['active_slot']!=save_enrollment:raise ValueError('Select the wireless slot before enrolling it')
   enrollment=enroll(board,devices,save_enrollment)
  else:enrollment=None
  proof,reason=evidence(status,board,devices,load_bindings()) if status['helper_protocol']==1 else (None,'Firmware lacks the host-evidence protocol')
  result={'observed_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'active_slot':status['active_slot'],'host_os':'Mac' if sys.platform=='darwin' else 'Windows' if sys.platform=='win32' else 'unsupported','local_wireless_slots':[d['slot'] for d in devices],'dry_run':dry_run,'os_action':'pending' if proof else 'unchanged','reason':reason}
  if enrollment:result['enrollment']=enrollment
  if proof:
   if status['helper_protocol']!=1:raise RuntimeError('Install firmware with the host-evidence protocol before applying OS hints')
   if status['evidence_mask']&(1<<proof['slot']) and status['os'][proof['slot']]==proof['os']:result['os_action']='already_confirmed'
   elif not dry_run:
    applied=keyboard.report_host_os(**proof);result['os_action']='confirmed';result['evidence_mask']=applied['evidence_mask'];result['hints_accepted']=applied['hints_accepted']
  if allow_clock and (sync or not status.get('clock_synced')) and not dry_run:
   local=time.localtime();result.update(keyboard.sync_clock(local.tm_hour*3600+local.tm_min*60+local.tm_sec))
  result['writes_flash']=False;result['reads_keystrokes']=False;return result

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--enroll',type=int,choices=range(1,5),help='Bind the currently selected, locally connected wireless device to this USB keyboard; confirm the physical device first')
 p.add_argument('--dry-run',action='store_true');group=p.add_mutually_exclusive_group();group.add_argument('--watch-seconds',type=int,default=0,help='Bounded foreground watch; zero runs once');group.add_argument('--watch',action='store_true',help='Run continuously as the user host-helper service')
 p.add_argument('--no-clock',action='store_true');a=p.parse_args()
 if a.watch_seconds<0 or a.watch_seconds>3600:p.error('Watch duration must be 0..3600 seconds')
 stopping=threading.Event()
 for sig in (signal.SIGTERM,signal.SIGINT):signal.signal(sig,lambda *_:stopping.set())
 deadline=time.monotonic()+a.watch_seconds;last=None;schedule=ClockSchedule();first=True
 owner=TransportLock(0,ROOT/'.runtime/host-helper-service.lock') if a.watch or a.watch_seconds else contextlib.nullcontext()
 with owner:
  if a.watch or a.watch_seconds:print(json.dumps({'service':'started','pid':os.getpid(),'version':1,'reads_keystrokes':False}),flush=True)
  while not stopping.is_set() and (first or a.watch or time.monotonic()<deadline):
   first=False
   try:
    monotonic=time.monotonic();wall=time.time();offset=int(datetime.datetime.now().astimezone().utcoffset().total_seconds())
    sync=not a.no_clock and schedule.due(monotonic,wall,offset)
    result=once(sync,a.dry_run,a.enroll,allow_clock=not a.no_clock);a.enroll=None
    schedule.observe(monotonic,wall,offset,bool(result.get('clock_synced')))
    compact={k:v for k,v in result.items() if k not in ('observed_at','hints_accepted')}
    if compact!=last:print(json.dumps(result),flush=True);last=compact
   except (OSError,RuntimeError,ValueError,hid.HIDException) as error:
    result={'error':str(error),'reads_keystrokes':False}
    if result!=last:print(json.dumps(result),flush=True);last=result
    if not (a.watch or a.watch_seconds):raise SystemExit(1)
   if not a.watch and time.monotonic()>=deadline:break
   stopping.wait(2 if a.watch else min(2,max(0,deadline-time.monotonic())))
  if a.watch or a.watch_seconds:print(json.dumps({'service':'stopped','pid':os.getpid()}),flush=True)
if __name__=='__main__':main()
