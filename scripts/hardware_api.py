"""Same-origin, CSRF-protected bridge to the fixed keyboard settings protocol."""
import json,secrets,sys,threading
from pathlib import Path
from keyboard_customize import Keyboard,decode,encode
from host_display import bluetooth_access,bluetooth_display,display
from keyboard_bluetooth import BluetoothKeyboard
from hardware_progress import PROGRESS
from keyboard_connections import discover,select
TOKEN=secrets.token_urlsafe(32);LOCK=threading.Lock()
ROOT=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parents[1]))
LAYOUT=[dict(x['vendor_key'],matrix=x['scan_index']*6+x['sense_bit'],usage=int(x['stock_usage'],16)) for x in json.loads((ROOT/'firmware/targets/f75max/board-map.json').read_text(encoding='utf-8'))['matrix']['coordinates'] if x.get('vendor_key')]

def resolve_connection(body,probe):
 mode=body.get('transport','usb');identity=None
 if mode=='auto' or body.get('board_identity'):
  snapshot=discover(probe);choice=select(snapshot,mode)
  if not choice['ready']:raise RuntimeError(choice['reason'] or 'No keyboard connection is available.')
  if body.get('expected_transport') and choice['selected']!=body['expected_transport']:raise RuntimeError('The keyboard connection changed. Check the connection before retrying.')
  identity=choice['board_identity']
  if body.get('board_identity') and identity!=body['board_identity']:raise RuntimeError('A different keyboard is connected. Read it before applying settings.')
  mode=choice['selected']
 return mode,identity

def handle(handler):
 path=handler.path
 progress_path=path.startswith('/api/hardware/progress/')
 if path!='/api/hardware' and not progress_path:return False
 def respond(value,status=200):
  data=json.dumps(value,separators=(',',':')).encode();handler.send_response(status)
  handler.send_header('Content-Type','application/json');handler.send_header('Cache-Control','no-store');handler.send_header('Content-Length',str(len(data)));handler.end_headers();handler.wfile.write(data)
 host=handler.headers.get('Host','');address,port=handler.server.server_address[:2]
 allowed={f'{address}:{port}'}
 if address=='127.0.0.1':allowed.add(f'localhost:{port}')
 if host not in allowed:respond({'error':'Use the configured Tailscale address'},403);return True
 if progress_path:
  if handler.command!='GET' or not secrets.compare_digest(handler.headers.get('X-F75-CSRF',''),TOKEN):
   respond({'error':'Reload Studio to check progress'},403);return True
  value=PROGRESS.get(path.rsplit('/',1)[-1])
  respond(value if value is not None else {'state':'pending'},200)
  return True
 desktop=getattr(handler.server,'desktop',False)
 probe=getattr(handler.server,'bluetooth_status_probe',None) if desktop else None
 if handler.command=='GET':
  respond({'csrf':TOKEN,'layout':LAYOUT,'protocol':1,'desktop':desktop,'bluetooth_status':probe is not None,'bluetooth_settings':probe is not None});return True
 if handler.headers.get('Origin')!='http://'+host or not secrets.compare_digest(handler.headers.get('X-F75-CSRF',''),TOKEN):
  respond({'error':'Reload this page before applying settings'},403);return True
 if not LOCK.acquire(False):respond({'error':'Keyboard is busy; wait for the current request'},423);return True
 tracked=None
 try:
  length=int(handler.headers.get('Content-Length','0'))
  if not 0<length<=65536:raise ValueError('Invalid request size')
  body=json.loads(handler.rfile.read(length))
  action=body.get('action')
  if action=='connections':
   snapshot=discover(probe);snapshot['choice']=select(snapshot,body.get('transport','auto'));respond(snapshot);return True
  if desktop and probe is not None and action in ('bluetooth-access','bluetooth-request-access'):
   respond(bluetooth_access(probe,request=action=='bluetooth-request-access'))
   return True
  if desktop and action in ('display-info','display-set','display-clear'):
   transport,identity=resolve_connection(body,probe)
   fields=(action[8:],body.get('text',''),body.get('seconds',20))
   if transport=='bluetooth' and probe is not None:
    result=bluetooth_display(probe,*fields,board_identity=identity)
   elif transport=='usb':
    connection=Keyboard();connection.expected_board=identity
    with connection as keyboard:
     result=display(keyboard,*fields)
   else:raise ValueError('This status connection is unavailable.')
   result['transport']=transport;result['board_identity']=identity
   respond(result)
   return True
  if action not in ('read','apply','save','clock'):raise ValueError('Unknown hardware action')
  if body.get('operation_id') is not None:
   PROGRESS.begin(body['operation_id'],action);tracked=body['operation_id']
  transport,identity=resolve_connection(body,probe)
  if transport=='bluetooth' and probe is not None:connection=BluetoothKeyboard(probe,fast=True)
  elif transport=='usb':connection=Keyboard()
  else:raise ValueError('This settings connection is unavailable.')
  verifying=False
  def report(phase,completed=None,total=None):
   if tracked:PROGRESS.update(tracked,'verifying' if verifying and phase in ('reading','checking') else phase,completed,total)
  connection.progress=report;connection.expected_board=identity
  with connection as keyboard:
   if body['action']=='clock':
    report('clock');result=keyboard.sync_clock(body['seconds'])
   elif body['action']=='read':result={'document':decode(keyboard.read()),'read':True}
   else:
    data=encode(body['document'])
    if transport=='bluetooth':result=keyboard.apply(data,body['action']=='save',baseline=bytes.fromhex(body['document']['base_hex']))
    else:result=keyboard.apply(data,body['action']=='save')
    verifying=True;report('verifying')
    actual=keyboard.verify(data) if transport=='bluetooth' else keyboard.read()
    result['verification']='snapshot-crc32' if transport=='bluetooth' else 'full-readback'
    if actual[160:]!=data[160:]:raise RuntimeError('Custom settings readback differs; read the keyboard before trying again')
    result['document']=decode(actual);result['custom_readback_verified']=True
    expected=decode(data)
    for key in ['names','lighting','light_mode','reduced_motion','screen_color','companion','power','wheel','indicators']:
     if result['document'][key]!=expected[key]:raise RuntimeError('Settings readback differs: '+key)
   if body['action']!='clock':
    result['host_status']=keyboard.host_status()
    result['document']['indicator_supported']=bool((result['host_status'] or {}).get('indicator_supported') or getattr(keyboard,'indicator_support',False))
    result['document']['bluetooth_clock_supported']=bool((result['host_status'] or {}).get('bluetooth_clock_supported') or getattr(keyboard,'clock_support',False))
  result['transport']=transport;result['board_identity']=identity
  if tracked:PROGRESS.finish(tracked,True)
  respond(result)
 except Exception as error:
  if tracked:PROGRESS.finish(tracked,False)
  respond({'error':str(error)},409)
 finally:LOCK.release()
 return True
