'use strict';
const $=s=>document.querySelector(s);
const transferProgress=new F75TransferProgress($('#transfer-progress'));
const colorPresets=[['Mint','#91e2ce'],['Rose','#f2a4aa'],['Lilac','#c4b4ef'],['Ocean','#a4c8f2'],['Peach','#edc08c'],['White','#ffffff'],['Blossom','#ffd3e7'],['Buttercream','#fff0b3'],['Seafoam','#c0f2df'],['Periwinkle','#b3bfff'],['Candy','#ff75b5'],['Coral','#ff806f'],['Cherry','#ed4667'],['Tangerine','#ff9b45'],['Sunflower','#ffd447'],['Lime','#b9ef61'],['Jade','#42d69b'],['Teal','#32bcb4'],['Cyan','#59dcf2'],['Azure','#4ba4ff'],['Indigo','#8072ee'],['Violet','#bd75f2'],['Fuchsia','#ed63d2'],['Warm white','#ffedd6']];
let settings=null,observedHost=null,csrf='',layout=[],chosen=null,layer=0,slot=0,busy=false,dirty=false;
let desktop=false,displayReady=false,bluetoothAccess=null;

// Sidebar navigation changes the visible settings pane without discarding edits.
let activeSection='keys';
function showSection(section,focus=false){
 const link=document.querySelector(`[data-section="${section}"]`);
 if(!link||link.hidden)section='keys';
 activeSection=section;
 for(const pane of document.querySelectorAll('[data-section-panel]'))pane.hidden=pane.dataset.sectionPanel!==section;
 for(const item of document.querySelectorAll('[data-section]')){
  if(item.dataset.section===section)item.setAttribute('aria-current','page');
  else item.removeAttribute('aria-current');
 }
 const current=document.querySelector(`[data-section="${section}"]`);
 $('#section-title').textContent=current.textContent;
 $('.preview').hidden=section==='macros'||section==='status';
 $('#editor').hidden=section==='status';
 $('#apply-note').hidden=section==='status';
 if(focus)$('#section-title').focus({preventScroll:true});
 window.scrollTo({top:0,behavior:'instant'});
}
for(const link of document.querySelectorAll('[data-section]'))link.addEventListener('click',event=>{
 event.preventDefault();history.replaceState(null,'',link.getAttribute('href'));showSection(link.dataset.section,true);
});
showSection('keys');

const reserved=new Set([0,7,13,19,25,31,41,52,62,71,84]);
const names={224:'Left Ctrl',225:'Left Shift',226:'Left Alt / Option',227:'Left Command / Windows',228:'Right Ctrl',229:'Right Shift',230:'Right Alt / Option',231:'Right Command / Windows',256:'Primary (Cmd / Ctrl)'};
const logicalKeys=()=>[...new Map(F75_LAYOUT.filter(k=>k.label!=='Fn').map(k=>[k.usage,names[k.usage]||k.label])).entries()].concat([[228,'Right Ctrl'],[231,'Right Command / Windows']]);
function option(select,value,label){const o=document.createElement('option');o.value=value;o.textContent=label;select.append(o);}
function mark(){transferProgress.dismiss();dirty=true;$('#state-label').textContent='Unapplied changes';updateButtons();paint();}
function updateButtons(){
 const invalid=!!$('#editor input:invalid');
 $('#editor').disabled=busy||!settings;$('#read').disabled=busy||($('#settings-transport').value==='bluetooth'&&bluetoothAccess!==null&&bluetoothAccess!=='granted');
 $('#apply').disabled=busy||!settings||!dirty||invalid;$('#save-board').disabled=busy||!settings||invalid;
 $('#read').textContent=busy?'Working…':'Read keyboard';
 $('#display-send').disabled=busy||!displayReady;
 $('#display-clear').disabled=busy||!displayReady;
 $('#display-transport').disabled=busy;
 $('#display-check').disabled=busy;
 $('#settings-transport').disabled=busy||dirty;
 $('#bluetooth-allow').disabled=busy;$('#bluetooth-recheck').disabled=busy;
 $('#settings-connection-note').hidden=$('#settings-transport').value!=='bluetooth';
 $('#sync-clock').disabled=busy||!settings||$('#settings-transport').value==='bluetooth';
}
async function checkBluetoothAccess(request=false){
 if(busy)return;busy=true;updateButtons();
 try{
  const response=await fetch('/api/hardware',{method:'POST',headers:{'Content-Type':'application/json','X-F75-CSRF':csrf},body:JSON.stringify({action:request?'bluetooth-request-access':'bluetooth-access'})});
  const result=await response.json();if(!response.ok)throw Error(result.error||'Could not check permission.');
  bluetoothAccess=result.access;$('#bluetooth-access').hidden=result.access==='granted';
  $('#bluetooth-access-message').textContent=result.access==='granted'?'Bluetooth access is ready.':'Mac Input Monitoring lets Studio exchange settings with this Bluetooth keyboard. Studio does not record key codes or typed text. Enable F75 Studio in System Settings > Privacy & Security > Input Monitoring, then quit and reopen Studio.';
 }catch(error){$('#bluetooth-access').hidden=false;$('#bluetooth-access-message').textContent=error.message;}
 finally{busy=false;updateButtons();}
}
$('#bluetooth-allow').onclick=()=>checkBluetoothAccess(true);
$('#bluetooth-recheck').onclick=()=>checkBluetoothAccess();
async function send(action){
 if(busy)return;
 const operation_id=transferProgress.start(action,$('#settings-transport').value,csrf);
 busy=true;updateButtons();$('#message').textContent=action==='clock'?'Synchronizing clock…':action==='read'?'Reading keyboard…':action==='save'?'Applying and saving to keyboard…':'Applying settings…';
 if($('#settings-transport').value==='bluetooth')$('#message').textContent+=' Bluetooth may take a few minutes. Keep the keyboard connected.';
 try{
  const time=new Date();const seconds=time.getHours()*3600+time.getMinutes()*60+time.getSeconds();
  const response=await fetch('/api/hardware',{method:'POST',headers:{'Content-Type':'application/json','X-F75-CSRF':csrf},body:JSON.stringify({action,operation_id,document:settings,seconds,transport:$('#settings-transport').value})});
  const result=await response.json();if(!response.ok)throw Error(result.error||'Keyboard request failed');
  if(action==='clock'){transferProgress.finish(true);$('#message').textContent='Clock synchronized to this device’s local time.';return;}
  settings=result.document;observedHost=result.host_status;dirty=false;
  $('#state-label').textContent=action==='save'?'Saved to keyboard':action==='apply'?'Applied · not saved':'Current keyboard settings';
  $('#message').textContent=action==='save'?'Settings saved and read back from your keyboard.':action==='apply'?'Settings applied and read back. Save to keep them after a restart.':'Keyboard settings loaded. Choose a key or edit a macro.';
  render();transferProgress.finish(true);
 }catch(error){transferProgress.finish(false);$('#message').textContent=error.message;$('#state-label').textContent=dirty?'Changes kept in editor':'Settings unavailable';}
 finally{busy=false;updateButtons();if(desktop && action==='read') await refreshDisplay();}
}
async function displayRequest(action, fields={}) {
 const response=await fetch('/api/hardware',{
  method:'POST', headers:{'Content-Type':'application/json','X-F75-CSRF':csrf},
  body:JSON.stringify({action:'display-'+action,transport:$('#display-transport').value,...fields})
 });
 const result=await response.json();
 if(!response.ok) throw Error(result.error || 'Keyboard display request failed');
 return result;
}
function displayAvailability(result) {
 displayReady=result.ready;
 if(result.transport==='bluetooth') return 'Mac ready to send. The keyboard needs Bluetooth status firmware.';
 if(!result.supported) return 'Update the keyboard firmware to show computer status.';
 if(!result.ready) return 'Select USB on the keyboard to show computer status.';
 return result.active?'A message is active.':'Ready to show a message.';
}
async function refreshDisplay() {
 if(busy)return;
 busy=true;displayReady=false;updateButtons();
 const message=$('#display-message');
 message.textContent='Checking status connection…';
 try { message.textContent=displayAvailability(await displayRequest('info')); }
 catch(error) { message.textContent=error.message; }
 finally {busy=false;updateButtons();}
}
async function sendDisplay(action) {
 if(busy)return;
 busy=true;
 updateButtons();
 const message=$('#display-message');
 message.textContent='Sending status request…';
 try {
  const result=await displayRequest(action,{
   text:$('#display-text').value.trim(),seconds:Number($('#display-duration').value)
  });
  const availability=displayAvailability(result);
  message.textContent=result.transport==='bluetooth' && result.reports_written
   ? 'Bluetooth reports sent. Check the keyboard’s Home screen.'
   : result.ready && action==='set'?'Status sent to the keyboard.':availability;
 } catch(error) {
  message.textContent=error.message;
 } finally {
  busy=false;
  updateButtons();
 }
}
function paint(){
 if(!settings)return;
 for(const key of F75_LAYOUT){const b=$(`[data-key="${key.id}"]`),real=layout.find(x=>String(x.key_index)===key.id);if(!real)continue;
  b.setAttribute('aria-pressed',String(chosen?.matrix===real.matrix));
  const color=settings.colors[layer][real.matrix]||settings.layer_colors[layer]||settings.colors[0][real.matrix]||'#a8ead4';b.style.setProperty('--key-color',color);
 }
}
function selection(){
 $('#selected-name').textContent=chosen?'Key · '+chosen.name:'Select a key';
 const select=$('#binding');select.replaceChildren();option(select,0,'Original action');option(select,65535,'Disabled');
 for(const [usage,label] of logicalKeys())option(select,usage,label);
 for(let i=0;i<8;i++)option(select,0x8000+i,'Macro '+(i+1));
 for(const [value,label] of [[0x40e9,'Volume up'],[0x40ea,'Volume down'],[0x40e2,'Mute'],[0x40cd,'Play / pause'],[0x2001,'Scroll up'],[0x2002,'Scroll down'],[0x2011,'Left mouse click'],[0x2012,'Right mouse click'],[0x2013,'Middle mouse click']])option(select,value,label);
 const locked=!chosen||layer===2||chosen.matrix===71||(layer===1&&reserved.has(chosen.matrix));
 select.disabled=locked;select.value=chosen&&layer<2?settings.keys[layer][chosen.matrix]:0;
 $('#binding-note').textContent=layer===2?'The Control layer uses the keyboard’s navigation controls. Its colors can be customized.':locked&&chosen?'This key is reserved for Fn, device switching or recovery. Its color can still change.':'Original follows the host layout: Caps sends Command on Mac and Ctrl on Windows or Android. Custom actions send their named keys.';
 $('#paint-key').disabled=!chosen;$('#inherit-key').disabled=!chosen;
 if(chosen&&settings.colors[layer][chosen.matrix])$('#paint').value=settings.colors[layer][chosen.matrix];paint();
}
function osMark(kind){
 const icon=F75_OS_ICONS[kind]||F75_OS_ICONS[0],ns='http://www.w3.org/2000/svg',svg=document.createElementNS(ns,'svg');
 svg.setAttribute('viewBox',`0 0 ${icon.size} ${icon.size}`);svg.setAttribute('class','os-profile-icon');svg.setAttribute('aria-hidden','true');
 for(let alpha=1;alpha<=15;alpha++){
  let d='';icon.pixels.forEach((pixel,index)=>{if(pixel===alpha)d+=`M${index%icon.size} ${Math.floor(index/icon.size)}h1v1h-1z`;});
  if(!d)continue;const path=document.createElementNS(ns,'path');path.setAttribute('d',d);path.setAttribute('fill','currentColor');path.setAttribute('opacity',String(alpha/15));svg.append(path);
 }
 return svg;
}
function profiles(){
 const container=$('#profiles');container.replaceChildren();
 for(let i=0;i<5;i++){
  const label=document.createElement('label');label.className='field';const span=document.createElement('span');span.textContent=['USB','Bluetooth 1','Bluetooth 2','Bluetooth 3','Receiver'][i];span.prepend(osMark(settings.os[i]));label.append(span);
  const osName=['Mac','Windows','Android'][settings.os[i]];
  const select=document.createElement('select');option(select,'auto','Auto · '+osName);option(select,'0','Mac');option(select,'1','Windows');option(select,'2','Android');
  select.value=settings.auto_mask&(1<<i)?'auto':String(settings.os[i]);select.onchange=()=>{if(select.value==='auto')settings.auto_mask|=1<<i;else{settings.auto_mask&=~(1<<i);settings.os[i]=Number(select.value);}mark();profiles();};label.append(select);const name=document.createElement('input');name.type='text';name.maxLength=18;name.value=settings.names[i];name.setAttribute('aria-label',['USB','Bluetooth 1','Bluetooth 2','Bluetooth 3','Receiver'][i]+' name');name.oninput=()=>{settings.names[i]=name.value;mark();};label.append(name);container.append(label);
 }
 $('#caps').checked=settings.caps_swap;
}
function macro(){
 const m=settings.macros[slot];$('#repeat').checked=m.repeat;$('#steps').replaceChildren();$('#add-step').disabled=m.steps.length>=32;
 m.steps.forEach((step,index)=>{
  const row=document.createElement('div');row.className='macro-step';
  const actionLabel=document.createElement('label');actionLabel.textContent='Step '+(index+1);const action=document.createElement('select');for(const [v,n] of [['down','Press'],['up','Release'],['wait','Wait']])option(action,v,n);
  action.value=step.usage===0?'wait':step.usage&0x8000?'up':'down';actionLabel.append(action);row.append(actionLabel);
  const delayLabel=document.createElement('label');delayLabel.textContent='Delay before (ms)';const delay=document.createElement('input');delay.type='number';delay.min=0;delay.max=5000;delay.step=10;delay.value=step.delay_ms;delayLabel.append(delay);row.append(delayLabel);
  const keyLabel=document.createElement('label');keyLabel.className='step-key';keyLabel.textContent='Logical key';const key=document.createElement('select');option(key,256,names[256]);for(const [usage,label] of logicalKeys())option(key,usage,label);key.value=step.usage&0x7fff||256;key.disabled=action.value==='wait';keyLabel.append(key);row.append(keyLabel);
  const remove=document.createElement('button');remove.textContent='Remove';remove.setAttribute('aria-label','Remove step '+(index+1));remove.onclick=()=>{m.steps.splice(index,1);mark();macro();};row.append(remove);
  const move=document.createElement('button');move.textContent='Move up';move.disabled=!index;move.setAttribute('aria-label','Move step '+(index+1)+' up');move.onclick=()=>{[m.steps[index-1],m.steps[index]]=[m.steps[index],m.steps[index-1]];mark();macro();};row.append(move);
  const update=()=>{const ms=Number(delay.value);if(!Number.isInteger(ms)||ms<0||ms>5000){delay.setCustomValidity('Use 0 to 5000 milliseconds');delay.reportValidity();return;}delay.setCustomValidity('');step.delay_ms=ms;step.usage=action.value==='wait'?0:Number(key.value)|(action.value==='up'?0x8000:0);key.disabled=action.value==='wait';mark();};action.onchange=key.onchange=delay.onchange=update;
  $('#steps').append(row);
 });
}
function render(){selection();profiles();macro();$('#wheel-mode').value=settings.wheel??0;$('#power-mode').value=settings.power??0;$('#face').value=settings.face;$('#companion').value=settings.companion??3;$('#companion').disabled=(settings.record_version??0)<6;$('#companion-support').textContent=(settings.record_version??0)<6?'Install the companion firmware to change characters.':'';lighting();}
function lighting(){
 $('#main-color').value=settings.lighting.color;$('#light-effect').value=String(settings.lighting.effect);
 for(const [name,id] of [['brightness','light-brightness'],['speed','light-speed']]){$('#'+id).value=settings.lighting[name];$('#'+name+'-value').textContent=settings.lighting[name]+'%';}
 $('#quiet-motion').checked=settings.reduced_motion;$('#screen-theme').value=settings.light_mode?'1':'0';$('#screen-accent').value=settings.screen_color||'#91e2ce';
 $('#main-color-hex').value=settings.lighting.color.toUpperCase();$('#screen-accent-hex').value=settings.screen_color?.toUpperCase()||'';
 for(const id of ['main-color-hex','screen-accent-hex']){$('#'+id).setCustomValidity('');$('#'+id).setAttribute('aria-invalid','false');$('#'+id+'-error').textContent='';}
 for(const [id,color] of [['light-presets',settings.lighting.color],['screen-presets',settings.screen_color]])for(const b of $('#'+id).children)b.setAttribute('aria-pressed',String(b.dataset.color===color?.toLowerCase()));
 updateButtons();
}
for(const [id,label,set] of [['light-presets','Lighting',color=>settings.lighting.color=color],['screen-presets','Screen accent',color=>settings.screen_color=color]])for(const [name,color] of colorPresets){
 const b=document.createElement('button');b.type='button';b.className='swatch';b.style.setProperty('--swatch',color);b.dataset.color=color;b.title=name;b.setAttribute('aria-label',label+' color '+name);b.setAttribute('aria-pressed','false');b.onclick=()=>{set(color);mark();lighting();};$('#'+id).append(b);
}
function colorInput(picker,hex,set){
 const input=$('#'+hex),error=document.createElement('span');error.id=hex+'-error';error.className='color-error';error.setAttribute('role','status');input.closest('.color-entry').append(error);input.setAttribute('aria-describedby',error.id);
 $('#'+picker).oninput=()=>{set($('#'+picker).value);mark();lighting();};
 input.oninput=()=>{
  const value=input.value.trim(),match=/^#?([0-9a-f]{6})$/i.exec(value);
  input.setCustomValidity(match?'':'Enter six hex digits, such as #91E2CE.');
  if(match){set('#'+match[1].toLowerCase());mark();const start=input.selectionStart;lighting();input.setSelectionRange(start,start);}
  else updateButtons();
 };
 input.onblur=()=>{const invalid=!input.checkValidity();input.setAttribute('aria-invalid',String(invalid));error.textContent=invalid?'Use six hex digits, such as #91E2CE.':'';};
}
colorInput('main-color','main-color-hex',color=>settings.lighting.color=color);
colorInput('screen-accent','screen-accent-hex',color=>settings.screen_color=color);
$('#light-effect').onchange=()=>{settings.lighting.effect=Number($('#light-effect').value);mark();};
for(const [name,id] of [['brightness','light-brightness'],['speed','light-speed']])$('#'+id).oninput=()=>{settings.lighting[name]=Number($('#'+id).value);$('#'+name+'-value').textContent=settings.lighting[name]+'%';mark();};
$('#quiet-motion').onchange=()=>{settings.reduced_motion=$('#quiet-motion').checked;mark();};
$('#palette-all').onclick=()=>{settings.colors=settings.colors.map(layer=>layer.map(()=>null));settings.layer_colors=[null,null,null];mark();};
$('#screen-default').onclick=()=>{settings.screen_color=null;lighting();mark();};
$('#screen-theme').onchange=()=>{settings.light_mode=$('#screen-theme').value==='1';mark();};
$('#read').onclick=()=>send('read');$('#apply').onclick=()=>send('apply');$('#save-board').onclick=()=>send('save');
$('#layer').onchange=()=>{layer=Number($('#layer').value);if(settings)selection();};
$('#binding').onchange=()=>{settings.keys[layer][chosen.matrix]=Number($('#binding').value);mark();};
$('#paint-key').onclick=()=>{if(chosen){settings.colors[layer][chosen.matrix]=$('#paint').value;mark();}};
$('#inherit-key').onclick=()=>{if(chosen){settings.colors[layer][chosen.matrix]=null;mark();}};
$('#paint-layer').onclick=()=>{settings.layer_colors[layer]=$('#paint').value;mark();};$('#inherit-layer').onclick=()=>{settings.layer_colors[layer]=null;mark();};
$('#caps').onchange=()=>{settings.caps_swap=$('#caps').checked;mark();};
$('#companion').onchange=()=>{settings.companion=Number($('#companion').value);mark();};
$('#wheel-mode').onchange=()=>{settings.wheel=Number($('#wheel-mode').value);mark();};
$('#power-mode').onchange=()=>{settings.power=Number($('#power-mode').value);mark();};
$('#display-send').onclick=()=>sendDisplay('set');
$('#display-clear').onclick=()=>sendDisplay('clear');
$('#display-transport').onchange=async()=>{if($('#display-transport').value==='bluetooth')await checkBluetoothAccess();await refreshDisplay();};
$('#settings-transport').onchange=async()=>{
 transferProgress.dismiss();settings=null;observedHost=null;dirty=false;updateButtons();
 $('#state-label').textContent='Not read yet';
 $('#message').textContent=$('#settings-transport').value==='bluetooth'?'Select Bluetooth on the keyboard, connect this Mac, then read its settings. Clock sync currently uses USB.':'Read the keyboard over USB to load current settings.';
 if($('#settings-transport').value==='bluetooth')await checkBluetoothAccess();else $('#bluetooth-access').hidden=true;
};
$('#display-check').onclick=refreshDisplay;
$('#face').onchange=()=>{settings.face=Number($('#face').value);mark();};$('#sync-clock').onclick=()=>send('clock');
for(let i=0;i<8;i++)option($('#macro-slot'),i,'Macro '+(i+1));$('#macro-slot').onchange=()=>{slot=Number($('#macro-slot').value);macro();};
$('#repeat').onchange=()=>{settings.macros[slot].repeat=$('#repeat').checked;mark();};
$('#add-step').onclick=()=>{settings.macros[slot].steps.push({usage:0,delay_ms:50});mark();macro();};
$('#copy-preset').onclick=()=>{settings.macros[slot]={repeat:false,steps:[{usage:256,delay_ms:0},{usage:6,delay_ms:20},{usage:0x8006,delay_ms:30},{usage:0x8100,delay_ms:0}]};mark();macro();};
window.addEventListener('beforeunload',event=>{if(dirty){event.preventDefault();event.returnValue='';}});
(async()=>{
 try{
  const response=await fetch('/api/hardware');if(!response.ok)throw Error('Hardware editor unavailable');const data=await response.json();csrf=data.csrf;layout=data.layout;
  desktop=data.desktop===true;
  if(desktop){
   document.body.classList.add('desktop');
   $('#desktop-sections').hidden=false;
   document.querySelector('[data-section="status"]').hidden=false;
   $('#display-connection').hidden=data.bluetooth_status!==true;
   $('#settings-connection').hidden=data.bluetooth_settings!==true;
   if(data.bluetooth_settings===true)$('#connection-intro').textContent='Edit keyboard settings over USB or Bluetooth.';
  }
  showSection(document.querySelector(`[data-section][href="${location.hash}"]`)?.dataset.section||'keys');
  for(const key of F75_LAYOUT){const b=document.createElement('button');b.className='key';b.dataset.key=key.id;b.textContent=key.label;b.setAttribute('aria-label','Select '+key.label);b.setAttribute('aria-pressed','false');
   Object.assign(b.style,{left:key.x/660*100+'%',top:key.y/280*100+'%',width:key.w/660*100+'%',height:key.h/280*100+'%'});
   b.onclick=()=>{chosen=layout.find(x=>String(x.key_index)===key.id);selection();};$('#keyboard').append(b);
  }
  if(desktop) await send('read');
 }catch(error){$('#message').textContent=error.message;$('#read').disabled=true;}
})();
