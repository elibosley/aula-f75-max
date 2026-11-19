"""Real HTTP and rendered editor, with a simulated keyboard (never opens HID)."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tests'))
import desktop
import hardware_api
from keyboard_bluetooth import snapshot_crc
from test_bluetooth_host import fixture

root=Path(__file__).resolve().parents[1]
out=Path(tempfile.mkdtemp(prefix='autosave-ui-',dir=root/'.runtime'))
board='a'*64
state={'connected':True,'slot':2,'fail':False,'saves':[],'reads':0}
data=bytearray(fixture());data[4]=6;data[128]=25
# Use the real encoder to create a valid fixture with the companion field.
from keyboard_customize import decode
import struct,zlib
struct.pack_into('<I',data,156,zlib.crc32(data[:156]));data=bytes(data)

def discovery(probe):
 return {'usb':{'present':False,'available':False,'active_slot':None,'board_identity':board,'reason':'USB absent'},'bluetooth':{'available':state['connected'],'slot':state['slot'],'access':'granted','board_identity':board,'reason':'Keyboard disconnected'}}

class FakeKeyboard:
 indicator_support=clock_support=True
 def __init__(self,*args,**kwargs):pass
 def __enter__(self):return self
 def __exit__(self,*args):pass
 def read(self):
  state['reads']+=1;self.progress('reading',3232,3232);return data
 def host_status(self):return None
 def apply(self,value,save=False,baseline=None):
  global data
  assert save is True,'Autosave did not request persistence'
  assert snapshot_crc(baseline)==snapshot_crc(data),'A stale reply replaced the latest baseline'
  state['saves'].append({'wheel':decode(value)['wheel'],'brightness':decode(value)['lighting']['brightness'],'effect':decode(value)['lighting']['effect'],'saved':save})
  self.progress('saving');time.sleep(.55)
  if state['fail']:raise RuntimeError('Save result is unconfirmed. Reload before retrying.')
  data=value;return {'applied':True,'saved':True}
 def verify(self,value):assert value==data;return data
 def sync_clock(self,value):return {'clock':True}

class Handler(desktop.EditorRequest):
 def do_POST(self):
  global data
  if self.path=='/__test/state':
   change=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
   if change.get('legacy'):
    legacy=bytearray(data);legacy[128]=0;legacy[118]=2;struct.pack_into('<I',legacy,156,zlib.crc32(legacy[:156]));data=bytes(legacy)
   state.update(change);payload=json.dumps(state).encode()
   self.send_response(200);self.send_header('Content-Length',str(len(payload)));self.end_headers();self.wfile.write(payload)
  else:super().do_POST()

node=r'''
const assert=require('node:assert/strict'),{chromium}=require('playwright');
(async()=>{const [origin,out]=process.argv.slice(2),b=await chromium.launch({headless:true,channel:'chrome'});try{
 const p=await b.newPage({viewport:{width:1120,height:800},colorScheme:'light',reducedMotion:'reduce'}),errors=[];p.setDefaultTimeout(8000);p.on('pageerror',e=>errors.push(String(e)));
 const state=async value=>(await p.request.post(origin+'/__test/state',{data:value})).json();
 const refresh=()=>p.evaluate(()=>refreshConnection());
 const saved=()=>p.locator('#state-label').filter({hasText:'All changes saved'}).waitFor();
 await p.goto(origin+'/hardware.html');await p.locator('#state-label').filter({hasText:'Ready'}).waitFor();
 assert.equal(await p.locator('#apply').count(),0);assert.equal(await p.locator('#save-board').count(),0);assert.equal((await state({})).saves.length,0);
 await p.getByRole('link',{name:'Screen',exact:true}).click();await p.locator('#wheel-mode').selectOption('1');
 await p.locator('#state-label').filter({hasText:'Saving…'}).waitFor();assert.equal(await p.locator('#wheel-mode').isDisabled(),false);
 await p.locator('#wheel-mode').selectOption('2');await saved();assert.equal(await p.locator('#wheel-mode').inputValue(),'2');assert.equal((await state({})).saves.length,2);
 await p.getByRole('link',{name:'Lighting',exact:true}).click();const before=(await state({})).saves.length;
 await p.locator('#light-brightness').fill('80');await p.locator('#light-brightness').fill('70');await p.locator('#light-brightness').fill('60');await saved();assert.equal((await state({})).saves.length,before+1);
 await p.locator('#main-color-hex').fill('ab');await p.waitForTimeout(1100);assert.equal((await state({})).saves.length,before+1);
 await p.locator('#main-color-hex').fill('#FFAA00');await saved();
 assert.equal(await p.locator('#light-effect option').count(),25);assert.equal(await p.locator('#light-effect optgroup').count(),4);
 for(let effect=0;effect<25;effect++){
  await p.locator('#light-effect').selectOption(String(effect));await saved();
  assert.equal((await state({})).saves.at(-1).effect,effect);
 }
 await p.locator('#light-effect').selectOption('5');await saved();
 assert.equal(await p.locator('#main-color').isDisabled(),true);assert.equal(await p.locator('#light-speed').isDisabled(),false);
 assert.match(await p.locator('#effect-description').innerText(),/spectrum/);
 await p.screenshot({path:out+'/rainbow-wave-light.png'});
 await p.locator('#light-effect').selectOption('23');await saved();assert.equal(await p.locator('#light-speed').isDisabled(),true);
 await p.locator('#light-effect').selectOption('22');await saved();assert.equal(await p.locator('#main-color').isDisabled(),false);
 await p.locator('#light-effect').selectOption('2');await saved();

 assert(await p.evaluate(()=>document.querySelector('#settings-transport').getBoundingClientRect().right<=document.querySelector('#desktop-sections').getBoundingClientRect().right));
 await p.keyboard.press('Tab');await p.locator('#read').focus();assert(await p.locator('#read').evaluate(e=>e.matches(':focus-visible')));
 await p.screenshot({path:out+'/lighting-light.png'});
 await p.getByRole('link',{name:'Macros',exact:true}).click();await p.locator('#copy-preset').click();await saved();
 await p.getByRole('button',{name:'Remove step 4',exact:true}).click();await p.locator('#state-label').filter({hasText:'Finish editing'}).waitFor();const incomplete=(await state({})).saves.length;
 await p.waitForTimeout(1000);assert.equal((await state({})).saves.length,incomplete);await p.locator('#copy-preset').click();
 // Reverting an incomplete edit to the last saved state requires no flash write.
 await saved();assert.equal((await state({})).saves.length,incomplete);
 await p.getByRole('link',{name:'Screen',exact:true}).click();await state({fail:true});await p.locator('#wheel-mode').selectOption('0');
 await p.locator('#state-label').filter({hasText:'Not saved'}).waitFor();const failed=(await state({})).saves.length;
 await p.locator('#power-mode').selectOption('2');await p.waitForTimeout(1200);assert.equal((await state({})).saves.length,failed);
 await p.emulateMedia({colorScheme:'dark'});await p.screenshot({path:out+'/save-error-dark.png'});
 await state({fail:false});await p.locator('#retry-save').click();await saved();
 await p.locator('#wheel-mode').selectOption('1');await state({connected:false});await refresh();const disconnected=(await state({})).saves.length;await p.waitForTimeout(1200);assert.equal((await state({})).saves.length,disconnected);assert.equal(await p.locator('#wheel-mode').inputValue(),'1');
 await state({connected:true,slot:1});await refresh();await p.waitForTimeout(1200);assert.equal((await state({})).saves.length,disconnected);
 await state({slot:2});await refresh();await saved();
 await p.getByRole('link',{name:'Lighting',exact:true}).click();await p.screenshot({path:out+'/lighting-dark.png'});
 await p.setViewportSize({width:780,height:580});assert(await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));await p.screenshot({path:out+'/compact.png'});
 await p.setViewportSize({width:390,height:844});await p.emulateMedia({colorScheme:'light'});assert(await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));await p.screenshot({path:out+'/phone.png'});

 await state({legacy:true});await p.locator('#read').click();await p.locator('#state-label').filter({hasText:'Ready'}).waitFor();
 assert.equal(await p.locator('#light-effect option:disabled').count(),20);assert.match(await p.locator('#effect-support').innerText(),/unlock all 25/);
 const legacyWrites=(await state({})).saves.length;
 await p.locator('#light-effect').evaluate(e=>{e.value='24';e.dispatchEvent(new Event('change'));});await p.waitForTimeout(1000);
 assert.equal((await state({})).saves.length,legacyWrites);
 await p.screenshot({path:out+'/legacy-lighting-gate.png'});
 assert.deepEqual(errors,[]);console.log(JSON.stringify({status:'passed',hardware_accessed:false,checks:['25 effects saved and verified','grouped effects','palette and movement controls follow effect','legacy firmware blocks new effects without writes','automatic read without writes','no Apply or Save buttons','edit during save','newer edit and verified baseline retained','slider burst coalesced','partial hex blocked','incomplete macro blocked','no-op avoids flash','failed write never automatically retried','explicit retry','disconnect retains draft','slot change blocks save','light dark compact phone reduced motion'],state:await state({}),screenshots:out}));
}finally{await b.close();}})().catch(e=>{console.error(e);process.exitCode=1});
'''
with patch.object(desktop,'hid_backend',lambda:None),patch.object(hardware_api,'discover',discovery),patch.object(hardware_api,'BluetoothKeyboard',FakeKeyboard),patch.object(hardware_api,'Keyboard',FakeKeyboard),patch.object(hardware_api,'bluetooth_display',lambda *a,**k:dict(ready=True,supported=True,transport='bluetooth')),patch.object(desktop,'bluetooth_status_probe',lambda:'probe'),patch.object(desktop,'EditorRequest',Handler),desktop.editor_server() as origin:
 result=subprocess.run(['node','-',origin,str(out)],cwd=root,input=node,text=True,capture_output=True,timeout=180)
 (out/'stdout.log').write_text(result.stdout);(out/'stderr.log').write_text(result.stderr)
 print(result.stdout,result.stderr,flush=True)
 result.check_returncode()
 (out/'result.json').write_text(result.stdout)
 print('Evidence:',out)
