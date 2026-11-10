#!/usr/bin/env python3
"""Read or apply structured keyboard settings over its fixed raw-HID protocol."""
import argparse,contextlib,json,secrets,struct,time,zlib
from pathlib import Path
from keyboard_transport_lock import TransportLock
ROOT=Path(__file__).resolve().parents[1]
BUNDLE_BYTES=3232
class Keyboard:
 def __init__(self,lock_timeout=1.0):self.lock=TransportLock(lock_timeout)
 def __enter__(self):
  try:
   import hid
   self.lock.__enter__()
   devices=[d for d in hid.enumerate(0xfeed,0xf750) if d['usage_page']==0xff60]
   if len(devices)!=1:raise RuntimeError('Connect the keyboard USB cable; one diagnostics interface is required')
   self.device=hid.Device(path=devices[0]['path']);self.token=secrets.randbits(32) or 1;return self
  except BaseException:self.lock.__exit__();raise
 def __exit__(self,*exc):
  try:self.device.close()
  finally:self.lock.__exit__()
 def exchange(self,op,offset=0,payload=b''):
  if len(payload)>17:raise ValueError('Payload too long')
  nonce=secrets.token_bytes(4);packet=b'F75u'+nonce+struct.pack('<IBH',self.token,op,offset)+payload.ljust(17,b'\0')
  self.device.write(b'\0'+packet);reply=bytes(self.device.read(32,1500))
  if len(reply)!=32 or reply[:8]!=b'F75t'+nonce:raise RuntimeError('Keyboard reply mismatch')
  if reply[12]:raise RuntimeError('Keyboard rejected request: '+str(reply[12]))
  return reply
 def raw_request(self,magic,payload=b''):
  if len(magic)!=4 or len(payload)>24:raise ValueError('Invalid fixed request')
  nonce=secrets.token_bytes(4);self.device.write(b'\0'+magic+nonce+payload.ljust(24,b'\0'));reply=bytes(self.device.read(32,1500))
  if len(reply)!=32 or reply[4:8]!=nonce:raise RuntimeError('Keyboard reply mismatch')
  return reply
 def host_status(self):
  r=self.raw_request(b'F75o')
  if r[:4]!=b'F75p':raise RuntimeError('Invalid host status reply')
  return {'usb_detected':r[8],'auto_mask':r[9],'active_slot':r[10],'os':list(r[11:16]),'caps_swap':bool(r[16]),
          'evidence_mask':r[17],'helper_protocol':r[18],'radio_connected':bool(r[19]&1),'clock_synced':bool(r[19]&2),'transaction':struct.unpack_from('<I',r,20)[0],
          'hints_accepted':struct.unpack_from('<I',r,24)[0],'hints_rejected':struct.unpack_from('<I',r,28)[0]}
 def report_host_os(self,slot,os,transaction):
  if not 1<=slot<=4 or os not in (0,1) or not 0<transaction<2**32:raise ValueError('Invalid host evidence')
  r=self.raw_request(b'F75l',b'HOSTOS!!'+bytes([slot,os,0,0])+struct.pack('<I',transaction))
  if r[:4]!=b'F75q' or r[8]!=1:raise RuntimeError('Host hint rejected; route, connection or manual layout changed')
  deadline=time.monotonic()+1
  while time.monotonic()<deadline:
   status=self.host_status()
   if status['active_slot']!=slot or status['transaction']!=transaction:raise RuntimeError('Host route changed before OS hint applied')
   if status['evidence_mask']&(1<<slot) and status['os'][slot]==os:return status
   time.sleep(.02)
  raise RuntimeError('Host OS hint completion not confirmed')
 def read(self):
  self.exchange(4)
  try:return b''.join(self.exchange(5,offset)[15:32] for offset in range(0,BUNDLE_BYTES,17))[:BUNDLE_BYTES]
  finally:self.exchange(6)
 def apply(self,data,save=False):
  validate(data);self.exchange(1,BUNDLE_BYTES,struct.pack('<I',zlib.crc32(data)))
  try:
   for offset in range(0,len(data),17):self.exchange(2,offset,data[offset:offset+17])
   self.exchange(3,BUNDLE_BYTES,bytes([bool(save)]))
   deadline=time.monotonic()+4
   while time.monotonic()<deadline:
    phase=self.exchange(0)[18]
    if phase in (6,7):raise RuntimeError('Settings validation failed' if phase==6 else 'Settings applied, but flash Save failed')
    if phase==(5 if save else 4):return {'applied':True,'saved':bool(save)}
    time.sleep(.02)
   raise RuntimeError('Settings completion not observed; read device state before retrying')
  except BaseException:
   with contextlib.suppress(Exception):self.exchange(6)
   raise
 def sync_clock(self,seconds):
  if type(seconds) is not int or not 0<=seconds<86400:raise ValueError('Clock needs seconds since local midnight')
  nonce=secrets.token_bytes(4);packet=b'F75h'+nonce+b'TIMESET!'+struct.pack('<I',seconds)+bytes(12)
  self.device.write(b'\0'+packet);reply=bytes(self.device.read(32,1500))
  if len(reply)!=32 or reply[:8]!=b'F75i'+nonce or reply[8]!=1 or struct.unpack_from('<I',reply,12)[0]!=seconds:raise RuntimeError('Clock synchronization not confirmed')
  return {'clock_synced':True,'seconds':seconds}

def validate(data):
 if len(data)!=BUNDLE_BYTES:raise ValueError('Invalid settings size')
 for part,magic in [(data[:160],b'F75S'),(data[160:],b'F75C')]:
  if part[:4]!=magic or struct.unpack_from('<I',part,len(part)-4)[0]!=zlib.crc32(part[:-4]):raise ValueError('Invalid settings record CRC')

def decode(data):
 validate(data);core=data[:160];custom=data[160:];at=16
 keys=[list(struct.unpack_from('<90H',custom,at+layer*180)) for layer in range(2)];at+=360
 rgb=[['#'+custom[at+(layer*90+key)*3:at+(layer*90+key)*3+3].hex() for key in range(90)] for layer in range(3)];at+=810
 flags=custom[at:at+270];at+=270
 colors=[[rgb[layer][key] if flags[layer*90+key] else None for key in range(90)] for layer in range(3)]
 layers=['#'+custom[at+i*3:at+i*3+3].hex() for i in range(3)];at+=9
 mask=custom[at];at+=1;layers=[layers[i] if mask&(1<<i) else None for i in range(3)]
 lengths=custom[at:at+8];at+=8;repeat=custom[at:at+8];at+=8
 macros=[]
 for slot in range(8):
  steps=[dict(zip(['usage','delay_ms'],struct.unpack_from('<HH',custom,at+slot*128+i*4))) for i in range(lengths[slot])]
  macros.append({'repeat':bool(repeat[slot]),'steps':steps})
 return {'schema':1,'base_hex':data.hex(),'os':list(core[12:17]),'auto_mask':core[126],'caps_swap':bool(core[114]),'face':core[120],
         'names':[core[17+i*19:36+i*19].split(b'\0')[0].decode('ascii') for i in range(5)],
         'lighting':{'color':'#'+core[122:125].hex(),'brightness':core[116],'speed':core[117],'effect':core[118]},
         'light_mode':bool(core[125]),'reduced_motion':bool(core[121]),'companion':core[127] if core[4]>=6 else 3,'record_version':core[4],
         'screen_color':'#'+custom[2513:2516].hex() if custom[4]>=2 and custom[2512] else None,
         'keys':keys,'colors':colors,'layer_colors':layers,'macros':macros}

def encode(document):
 data=bytearray.fromhex(document['base_hex']);validate(data)
 def integer(v,low,high):
  if type(v) is not int or not low<=v<=high:raise ValueError('Setting outside supported range')
  return v
 def color(v):
  if not isinstance(v,str) or len(v)!=7 or v[0]!='#':raise ValueError('Color must be #RRGGBB')
  return bytes.fromhex(v[1:])
 data[12:17]=bytes(integer(x,0,2) for x in document['os']);data[126]=integer(document['auto_mask'],0,31)
 companion=document.get('companion',data[127] if data[4]>=6 else 3)
 companion=integer(companion,0,3)
 if data[4]>=6 or companion!=3:data[4]=6;data[127]=companion
 elif any(x==2 for x in document['os']):data[4]=5
 if len(document['os'])!=5:raise ValueError('Five host layouts required')
 if type(document['caps_swap']) is not bool:raise ValueError('Caps swap must be boolean')
 data[114]=document['caps_swap'];data[120]=integer(document.get('face',data[120]),0,3)
 if 'names' in document:
  if len(document['names'])!=5:raise ValueError('Five device names required')
  for i,name in enumerate(document['names']):
   if not isinstance(name,str) or not name.strip() or len(name)>18 or any(ord(c)<32 or ord(c)>126 for c in name):raise ValueError('Use 1–18 plain letters, numbers or punctuation for a device name')
   data[17+i*19:36+i*19]=name.encode('ascii').ljust(19,b'\0')
 if 'lighting' in document:
  lighting=document['lighting'];data[122:125]=color(lighting['color']);data[116]=integer(lighting['brightness'],0,100);data[117]=integer(lighting['speed'],0,100);data[118]=integer(lighting['effect'],0,4)
 for key,offset in [('light_mode',125),('reduced_motion',121)]:
  if key in document:
   if type(document[key]) is not bool:raise ValueError(key+' must be boolean')
   data[offset]=document[key]
 struct.pack_into('<I',data,156,zlib.crc32(data[:156]))
 custom=bytearray(3072);custom[:4]=b'F75C';custom[4]=1;struct.pack_into('<H',custom,6,3072);at=16
 if len(document['keys'])!=2 or any(len(layer)!=90 for layer in document['keys']):raise ValueError('Two key layers required')
 for layer in document['keys']:
  for usage in layer:struct.pack_into('<H',custom,at,integer(usage,0,65535));at+=2
 if len(document['colors'])!=3 or any(len(layer)!=90 for layer in document['colors']):raise ValueError('Three color layers required')
 flags=[]
 for layer in document['colors']:
  for value in layer:
   custom[at:at+3]=color(value) if value is not None else bytes(3);at+=3;flags.append(value is not None)
 custom[at:at+270]=bytes(flags);at+=270
 if len(document['layer_colors'])!=3:raise ValueError('Three layer colors required')
 mask=0
 for i,value in enumerate(document['layer_colors']):
  custom[at:at+3]=color(value) if value is not None else bytes(3);at+=3
  if value is not None:mask|=1<<i
 custom[at]=mask;at+=1
 macros=document['macros']
 if len(macros)!=8:raise ValueError('Eight macro slots required')
 for layer,keys in enumerate(document['keys']):
  for key,usage in enumerate(keys):
   if usage and (key in (71,84) or (layer==1 and key in (0,7,13,19,25,31,41,52,62))):raise ValueError('This key is reserved for Fn, switching or recovery')
   if 0x8000<=usage<0x8008 and not macros[usage-0x8000]['steps']:raise ValueError('Macro '+str(usage-0x8000+1)+' has no steps')
 for i,macro in enumerate(macros):
  if len(macro['steps'])>32 or type(macro['repeat']) is not bool:raise ValueError('Macro requires at most 32 steps and a boolean repeat flag')
  for primary in (0xe0,0xe3):
   held=set();duration=0
   for index,step in enumerate(macro['steps']):
    value=integer(step['usage'],0,65535);delay=integer(step['delay_ms'],0,5000);duration+=delay
    if duration>120000:raise ValueError('Macro '+str(i+1)+' exceeds two minutes')
    if not value:continue
    key=value&0x7fff
    if key!=256 and not 4<=key<=0xe7:raise ValueError('Invalid macro key')
    if key==256:key=primary
    if value&0x8000:
     if key not in held:raise ValueError('Macro '+str(i+1)+', step '+str(index+1)+': key is not pressed')
     held.remove(key)
    else:
     if key in held:raise ValueError('Macro '+str(i+1)+', step '+str(index+1)+': key is already pressed')
     held.add(key)
     if sum(key<0xe0 for key in held)>6:raise ValueError('A macro can hold at most six ordinary keys')
   if held:raise ValueError('Macro '+str(i+1)+': add releases for every pressed key')
  custom[at+i]=len(macro['steps']);custom[at+8+i]=macro['repeat']
 at+=16
 for macro in macros:
  for i in range(32):
   step=macro['steps'][i] if i<len(macro['steps']) else {'usage':0,'delay_ms':0}
   struct.pack_into('<HH',custom,at,integer(step['usage'],0,65535),integer(step['delay_ms'],0,5000));at+=4
 if document.get('screen_color') is not None:
  custom[4]=2;custom[2512]=1;custom[2513:2516]=color(document['screen_color'])
 struct.pack_into('<I',custom,3068,zlib.crc32(custom[:3068]));data[160:]=custom;return bytes(data)

def main():
 p=argparse.ArgumentParser();g=p.add_mutually_exclusive_group(required=True);g.add_argument('--read',type=Path);g.add_argument('--apply',type=Path);p.add_argument('--save',action='store_true');a=p.parse_args()
 with Keyboard() as k:
  if a.read:a.read.write_text(json.dumps(decode(k.read()),indent=2)+'\n');print(json.dumps({'read':str(a.read)}))
  else:
   data=encode(json.loads(a.apply.read_text()));result=k.apply(data,a.save);actual=k.read()
   if actual[160:]!=data[160:]:raise RuntimeError('Custom settings readback differs')
   print(json.dumps(result|{'custom_readback_verified':True}))
if __name__=='__main__':main()
