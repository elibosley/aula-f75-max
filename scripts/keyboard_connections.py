"""Read-only discovery and deterministic selection of the keyboard connection."""
import hashlib,json,re,subprocess
from keyboard_customize import Keyboard,hid_backend


def bluetooth_presence(probe):
 result={'available':False,'access':'unavailable','slot':None,'board_identity':None,'reason':'Bluetooth is unavailable in this installation.'}
 if probe is None:return result
 try:
  process=subprocess.run([str(probe),'--check'],capture_output=True,text=True,timeout=5)
  if process.returncode:
   result['reason']='Bluetooth enrollment is required.' if 'Enroll this keyboard' in process.stderr else 'Bluetooth discovery failed.'
   return result
  value=json.loads(process.stdout)
  if value.get('access') not in ('granted','denied','unknown'):raise ValueError('Invalid access state')
  matches=value.get('local_wireless_devices')
  if not isinstance(matches,list):raise ValueError('Missing device metadata')
  result['access']=value['access']
  valid=[x for x in matches if type(x.get('enrolled_owners')) is int and x['enrolled_owners']==1 and type(x.get('slot')) is int and x['slot'] in (1,2,3) and isinstance(x.get('board_identity'),str) and re.fullmatch('[0-9a-f]{64}',x['board_identity'])]
  if value.get('ambiguous') or len(valid)>1:result['reason']='More than one enrolled Bluetooth keyboard is connected.'
  elif len(valid)==1:
   result.update(available=True,slot=valid[0]['slot'],board_identity=valid[0]['board_identity'],reason='')
  else:result['reason']='No enrolled Bluetooth keyboard is connected.'
 except (OSError,subprocess.TimeoutExpired,ValueError,TypeError,AttributeError):result['reason']='Bluetooth discovery failed. Check the connection and try again.'
 return result


def discover(probe=None):
 usb={'available':False,'present':False,'active_slot':None,'board_identity':None,'reason':'No USB keyboard is connected.'}
 try:
  devices=[d for d in hid_backend().enumerate(0xfeed,0xf750) if d.get('usage_page')==0xff60]
  if len(devices)>1:usb.update(present=True,reason='More than one USB keyboard is connected.')
  elif devices:
   usb['present']=True;serial=devices[0].get('serial_number')
   if not isinstance(serial,str) or not serial:usb['reason']='USB keyboard has no stable identity.'
   else:
    usb['board_identity']=hashlib.sha256(serial.encode()).hexdigest()
    with Keyboard(lock_timeout=0) as keyboard:status=keyboard.host_status()
    slot=status['active_slot']
    if type(slot) is not int or slot not in range(5):raise ValueError('Invalid active route')
    usb.update(available=True,active_slot=slot,reason='')
 except Exception as error:
  # An error never means that USB is absent and never authorizes a switch.
  usb['reason']='USB connection could not be checked. Finish any active transfer, then check again.'
  usb['present']=True
 bluetooth=bluetooth_presence(probe)
 result={'usb':usb,'bluetooth':bluetooth}
 result.update(select(result,'auto'))
 return result


def select(snapshot,mode):
 usb=snapshot['usb'];bluetooth=snapshot['bluetooth'];selected=None;reason=''
 if mode=='usb':
  if usb['available']:selected='usb'
  else:reason=usb['reason']
 elif mode=='bluetooth':
  if bluetooth['available']:selected='bluetooth'
  else:reason=bluetooth['reason']
 elif mode=='auto':
  if usb['present']:
   if not usb['available']:reason=usb['reason']
   elif usb['active_slot'] in (1,2,3):
    if bluetooth['available'] and bluetooth['slot']==usb['active_slot'] and bluetooth['board_identity']==usb['board_identity']:selected='bluetooth'
    else:reason='The selected Bluetooth device is not connected to this computer. Choose USB explicitly to configure through the cable.'
   else:selected='usb'
  elif bluetooth['available']:selected='bluetooth'
  else:reason=bluetooth['reason'] if bluetooth['access']!='unavailable' else 'Connect your keyboard to this computer.'
 else:raise ValueError('Unknown connection mode')
 source=snapshot.get(selected,{}) if selected else {}
 ready=selected is not None and (selected!='bluetooth' or bluetooth['access']=='granted')
 if selected=='bluetooth' and not ready:reason='Allow F75 Studio in Mac Input Monitoring to use Bluetooth.'
 return {'selected':selected,'ready':ready,'reason':reason,'board_identity':source.get('board_identity'),'slot':bluetooth['slot'] if selected=='bluetooth' else None}
