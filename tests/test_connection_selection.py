"""Auto follows live routes and never turns a discovery or Save failure into another write."""
import contextlib,hashlib,io,json,sys,types,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import keyboard_connections as connections
import hardware_api
from keyboard_customize import decode
from test_bluetooth_host import fixture
BOARD=hashlib.sha256(b'board').hexdigest()
def snapshot(usb=False,slot=None,bluetooth=True,access='granted'):
 return {'usb':{'present':usb,'available':usb,'active_slot':slot,'board_identity':BOARD,'reason':'USB absent'},'bluetooth':{'available':bluetooth,'slot':2 if bluetooth else None,'access':access,'board_identity':BOARD,'reason':'Bluetooth absent'}}
class SelectionTest(unittest.TestCase):
 def test_auto_prefers_selected_usb_and_routes_bluetooth_even_with_cable(self):
  for state,transport in [(snapshot(False), 'bluetooth'),(snapshot(True,0),'usb'),(snapshot(True,2),'bluetooth'),(snapshot(True,4),'usb')]:
   with self.subTest(state=state):self.assertEqual(connections.select(state,'auto')['selected'],transport)
 def test_unverified_route_or_different_board_is_not_substituted(self):
  for mutate in [lambda s:s['usb'].update(available=False),lambda s:s['bluetooth'].update(slot=1),lambda s:s['bluetooth'].update(board_identity='b'*64)]:
   value=snapshot(True,2);mutate(value);self.assertIsNone(connections.select(value,'auto')['selected'])
 def test_permissions_stay_visible_and_explicit_usb_is_available(self):
  state=snapshot(True,2,access='denied');choice=connections.select(state,'auto')
  self.assertEqual(choice['selected'],'bluetooth');self.assertFalse(choice['ready']);self.assertIn('Input Monitoring',choice['reason'])
  self.assertTrue(connections.select(state,'usb')['ready'])
 def test_discovery_error_never_means_usb_is_absent(self):
  with patch.object(connections,'hid_backend',side_effect=OSError()),patch.object(connections,'bluetooth_presence',return_value=snapshot()['bluetooth']):
   result=connections.discover('probe')
  self.assertTrue(result['usb']['present']);self.assertFalse(result['ready']);self.assertIsNone(result['selected'])
 def test_presence_only_uses_check_and_does_not_request_access(self):
  response={'access':'granted','local_wireless_devices':[{'slot':2,'enrolled_owners':1,'board_identity':BOARD}]}
  with patch.object(connections.subprocess,'run',return_value=types.SimpleNamespace(returncode=0,stdout=json.dumps(response),stderr='')) as run:
   result=connections.bluetooth_presence('probe')
  self.assertTrue(result['available']);self.assertEqual(run.call_args.args[0],['probe','--check'])
  response['ambiguous']=True
  with patch.object(connections.subprocess,'run',return_value=types.SimpleNamespace(returncode=0,stdout=json.dumps(response),stderr='')):
   self.assertFalse(connections.bluetooth_presence('probe')['available'])
 def test_route_and_board_change_stop_before_opening(self):
  for fields in [{'expected_transport':'usb'},{'board_identity':'b'*64}]:
   with patch.object(hardware_api,'discover',return_value=snapshot()),self.assertRaises(RuntimeError):hardware_api.resolve_connection({'transport':'auto',**fields},'probe')
 def test_failed_save_is_sent_once_to_bluetooth_without_usb_retry(self):
  class Keyboard:
   commits=0
   def __enter__(self):return self
   def __exit__(self,*args):pass
   def apply(self,*args,**kwargs):type(self).commits+=1;raise RuntimeError('Save result is unconfirmed; read before retrying')
  payload=json.dumps({'action':'save','transport':'auto','expected_transport':'bluetooth','board_identity':BOARD,'document':decode(fixture())}).encode()
  handler=types.SimpleNamespace(path='/api/hardware',command='POST',headers={'Host':'127.0.0.1:1234','Origin':'http://127.0.0.1:1234','X-F75-CSRF':hardware_api.TOKEN,'Content-Length':str(len(payload))},server=types.SimpleNamespace(server_address=('127.0.0.1',1234),desktop=True,bluetooth_status_probe='probe'),rfile=io.BytesIO(payload),wfile=io.BytesIO(),send_response=lambda code:None,send_header=lambda *args:None,end_headers=lambda:None)
  with patch.object(hardware_api,'discover',return_value=snapshot()),patch.object(hardware_api,'BluetoothKeyboard',return_value=Keyboard()),patch.object(hardware_api,'Keyboard') as usb:
   hardware_api.handle(handler)
  usb.assert_not_called();self.assertEqual(Keyboard.commits,1);self.assertIn('unconfirmed',json.loads(handler.wfile.getvalue())['error'])
 def test_successful_bluetooth_save_verifies_crc_without_full_readback(self):
  calls=[]
  class Keyboard:
   indicator_support=True;clock_support=True
   def __enter__(self):return self
   def __exit__(self,*args):pass
   def apply(self,data,save=False,baseline=None):calls.append(('apply',save));return {'applied':True,'saved':save}
   def verify(self,data):calls.append(('verify',len(data)));return data
   def read(self):raise AssertionError('Save downloaded the full snapshot again')
   def host_status(self):return None
  payload=json.dumps({'action':'save','transport':'auto','expected_transport':'bluetooth','board_identity':BOARD,'document':decode(fixture())}).encode()
  handler=types.SimpleNamespace(path='/api/hardware',command='POST',headers={'Host':'127.0.0.1:1234','Origin':'http://127.0.0.1:1234','X-F75-CSRF':hardware_api.TOKEN,'Content-Length':str(len(payload))},server=types.SimpleNamespace(server_address=('127.0.0.1',1234),desktop=True,bluetooth_status_probe='probe'),rfile=io.BytesIO(payload),wfile=io.BytesIO(),send_response=lambda code:None,send_header=lambda *args:None,end_headers=lambda:None)
  with patch.object(hardware_api,'discover',return_value=snapshot()),patch.object(hardware_api,'BluetoothKeyboard',return_value=Keyboard()),patch.object(hardware_api,'Keyboard') as usb:
   hardware_api.handle(handler)
  usb.assert_not_called();result=json.loads(handler.wfile.getvalue());self.assertNotIn('error',result)
  self.assertEqual(calls,[('apply',True),('verify',3232)]);self.assertEqual(result['verification'],'snapshot-crc32');self.assertEqual(result['transport'],'bluetooth')
if __name__=='__main__':unittest.main()
