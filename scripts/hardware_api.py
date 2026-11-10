"""Same-origin, CSRF-protected bridge to the fixed keyboard settings protocol."""
import json,secrets,threading
from pathlib import Path
from keyboard_customize import Keyboard,decode,encode
TOKEN=secrets.token_urlsafe(32);LOCK=threading.Lock()
ROOT=Path(__file__).resolve().parents[1]
LAYOUT=[dict(x['vendor_key'],matrix=x['scan_index']*6+x['sense_bit'],usage=int(x['stock_usage'],16)) for x in json.loads((ROOT/'firmware/targets/f75max/board-map.json').read_text())['matrix']['coordinates'] if x.get('vendor_key')]

def handle(handler):
 path=handler.path
 if path!='/api/hardware':return False
 def respond(value,status=200):
  data=json.dumps(value,separators=(',',':')).encode();handler.send_response(status)
  handler.send_header('Content-Type','application/json');handler.send_header('Cache-Control','no-store');handler.send_header('Content-Length',str(len(data)));handler.end_headers();handler.wfile.write(data)
 host=handler.headers.get('Host','');address,port=handler.server.server_address[:2]
 allowed={f'{address}:{port}'}
 if address=='127.0.0.1':allowed.add(f'localhost:{port}')
 if host not in allowed:respond({'error':'Use the configured Tailscale address'},403);return True
 if handler.command=='GET':respond({'csrf':TOKEN,'layout':LAYOUT,'protocol':1});return True
 if handler.headers.get('Origin')!='http://'+host or not secrets.compare_digest(handler.headers.get('X-F75-CSRF',''),TOKEN):
  respond({'error':'Reload this page before applying settings'},403);return True
 if not LOCK.acquire(False):respond({'error':'Keyboard is busy; wait for the current request'},423);return True
 try:
  length=int(handler.headers.get('Content-Length','0'))
  if not 0<length<=65536:raise ValueError('Invalid request size')
  body=json.loads(handler.rfile.read(length))
  if body.get('action') not in ('read','apply','save','clock'):raise ValueError('Unknown hardware action')
  with Keyboard() as keyboard:
   if body['action']=='clock':result=keyboard.sync_clock(body['seconds'])
   elif body['action']=='read':result={'document':decode(keyboard.read()),'read':True}
   else:
    data=encode(body['document']);result=keyboard.apply(data,body['action']=='save');actual=keyboard.read()
    if actual[160:]!=data[160:]:raise RuntimeError('Custom settings readback differs; read the keyboard before trying again')
    result['document']=decode(actual);result['custom_readback_verified']=True
    expected=decode(data)
    for key in ['names','lighting','light_mode','reduced_motion','screen_color','companion']:
     if result['document'][key]!=expected[key]:raise RuntimeError('Settings readback differs: '+key)
   if body['action']!='clock':result['host_status']=keyboard.host_status()
  respond(result)
 except Exception as error:respond({'error':str(error)},409)
 finally:LOCK.release()
 return True
