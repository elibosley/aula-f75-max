#!/usr/bin/env python3
"""Send configuration transactions through actual ARM USB and observe key reports."""
import argparse,hashlib,json,struct,zlib
from pathlib import Path
from system_emulator import System,HOST
from test_system_emulator import enumerate_usb
from keyboard_customize import decode,encode

def run(image):
 with System(image) as m:
  enumerate_usb(m)
  reports=[]
  def advance(ms=5):
   m.write32(HOST+0x30,0);m.advance(ms);m.pump()
   for _ in range(20):
    packet=m.endpoint_in(1)
    if packet is None:break
    reports.append(packet)
  def request(op,offset=0,payload=b'',token=0x12345678):
   packet=b'F75utest'+struct.pack('<IBH',token,op,offset)+payload.ljust(17,b'\0')
   m.endpoint_out(3,packet);advance();r=m.endpoint_in(2);assert r and r[:8]==b'F75ttest',r;return r
  def download():
   assert request(4)[12]==0
   data=b''.join(request(5,offset)[15:32] for offset in range(0,3232,17))[:3232];request(6);return data
  def upload(data,save=False):
   assert request(1,3232,struct.pack('<I',zlib.crc32(data)))[12]==0
   for offset in range(0,3232,17):assert request(2,offset,data[offset:offset+17])[12]==0
   assert request(3,3232,bytes([save]))[12]==0
   return request(0)[18]
  advance(400);original=download();doc=decode(original)
  def sync_clock(seconds):
   m.endpoint_out(3,b'F75htimeTIMESET!'+struct.pack('<I',seconds)+bytes(12));advance();r=m.endpoint_in(2);assert r[:8]==b'F75itime';return r[8]
  assert sync_clock(86399)==1;advance(1100)
  assert m.read(m.symbols['clock_state'],4)==bytes(4),'Clock did not wrap midnight'
  assert sync_clock(86400)==0;assert m.read(m.symbols['clock_state'],4)==bytes(4)
  assert encode(doc)==original,'Python codec and firmware disagree'
  keymap=struct.unpack('<90H',m.read(m.symbols['keymaps'],180))
  def key(usage,down):
   row,col=divmod(keymap.index(usage),6);m.write32(HOST+0x100+row*4,(1<<col) if down else 0);advance(20)
  # A remap and a Primary+C macro on B, with an explicit Windows profile.
  doc['auto_mask']=0;doc['os'][0]=1;doc['keys'][0][keymap.index(4)]=5
  doc['keys'][0][keymap.index(5)]=0x8000
  doc['macros'][0]={'repeat':False,'steps':[{'usage':0x100,'delay_ms':0},{'usage':6,'delay_ms':10},{'usage':0x8006,'delay_ms':30},{'usage':0x8100,'delay_ms':0}]}
  doc['colors'][0][keymap.index(4)]='#ff0000';doc['layer_colors'][1]='#00ff00';blob=encode(doc)
  assert upload(blob,True)==5;readback=download();assert readback==blob
  def pwm():
   advance(100);active=m.read(m.symbols['active_buffer'],1)[0];return m.read(m.symbols['duties']+active*270,270)
  index=keymap.index(4);led=(index%6)*15+index//6;colors=pwm()
  assert colors[led]>0 and colors[90+led]==colors[180+led]==0,'Base per-key paint missing'
  m.write32(HOST+0x100+11*4,1<<5);advance(20);colors=pwm()
  assert colors[led]==0 and colors[90+led]>0 and colors[180+led]==0,'Fn layer color missing'
  m.write32(HOST+0x100+11*4,0);advance(20)
  # Rejected partial or bad transactions cannot change the active profile.
  assert request(1,3232,struct.pack('<I',0))[12]==0
  assert request(2,17,bytes(17))[12]==3
  assert request(3,3232,b'\0')[12]==3
  request(6);assert download()==blob
  invalid=decode(blob);invalid['macros'][0]['steps'].pop()
  try:encode(invalid);raise AssertionError('Host accepted a stuck macro')
  except ValueError:pass
  malformed=bytearray(blob);malformed[160+1466]=3;struct.pack_into('<I',malformed,3228,zlib.crc32(malformed[160:3228]));assert upload(malformed)==6
  assert download()==blob
  # Actual interrupt-IN reports prove remap and modifier ownership.
  def report():return reports[-1]
  key(4,True);assert report()[2:]==bytes([5,0,0,0,0,0]),report();key(4,False)
  key(0x39,True);assert report()[0]&1
  key(5,True)
  for _ in range(20):advance(5)
  assert report()[0]&1,'Macro released physical Ctrl owner'
  key(5,False);key(0x39,False);assert report()==bytes(8),report()
  # Original physical keys use the Mac policy, but an explicit logical Ctrl binding remains Ctrl.
  macdoc=decode(blob);macdoc['os'][0]=0;macdoc['keys'][0][keymap.index(4)]=0xe0
  assert upload(encode(macdoc))==4
  key(0x39,True);assert report()[0]==8,'Mac Caps did not emit Command';key(0x39,False)
  key(4,True);assert report()[0]==1,'Explicit logical Ctrl was changed to Command';key(4,False)
  # Cancel in-flight macro on OS/profile change and preserve recovery shortcuts.
  key(5,True);assert upload(original)==4;key(5,False);assert report()==bytes(8)
  # New color/name fields round-trip through real USB and Save, including a
  # version-2 screen accent while the legacy custom record remains accepted.
  colors=decode(original);colors['lighting']={'color':'#f2a4aa','brightness':53,'speed':41,'effect':0};colors['screen_color']='#c4b4ef';colors['names'][2]='Tablet'
  extended=encode(colors);assert upload(extended,True)==5;readback=decode(download())
  assert readback['lighting']==colors['lighting'] and readback['screen_color']==colors['screen_color'] and readback['names']==colors['names']
  assert download()[164]==2
  assert upload(original)==4
 return {'status':'passed','candidate_sha256':hashlib.sha256(Path(image).read_bytes()).hexdigest(),'hardware_writes':False,'real_usb_configuration_roundtrip':True,'python_and_firmware_codec_match':True,'reject_incomplete_and_invalid_macros':True,'base_key_and_fn_layer_pwm':True,'remap_usb_report':True,'macro_does_not_release_physical_modifier':True,'apply_cancels_macro':True,'custom_save_commits':True,'clock_sync_midnight_and_invalid_time':True,'lighting_screen_accent_and_device_names_roundtrip':True}
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('image',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args();r=run(a.image);a.output.write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r))
