'use strict';
const $=s=>document.querySelector(s);
const transferProgress=new F75TransferProgress($('#transfer-progress'));
const colorPresets=[['Mint','#91e2ce'],['Rose','#f2a4aa'],['Lilac','#c4b4ef'],['Ocean','#a4c8f2'],['Peach','#edc08c'],['White','#ffffff'],['Blossom','#ffd3e7'],['Buttercream','#fff0b3'],['Seafoam','#c0f2df'],['Periwinkle','#b3bfff'],['Candy','#ff75b5'],['Coral','#ff806f'],['Cherry','#ed4667'],['Tangerine','#ff9b45'],['Sunflower','#ffd447'],['Lime','#b9ef61'],['Jade','#42d69b'],['Teal','#32bcb4'],['Cyan','#59dcf2'],['Azure','#4ba4ff'],['Indigo','#8072ee'],['Violet','#bd75f2'],['Fuchsia','#ed63d2'],['Warm white','#ffedd6']];
let settings=null,observedHost=null,csrf='',layout=[],chosen=null,layer=0,slot=0,busy=false,dirty=false;
let desktop=false,displayReady=false,bluetoothAccess=null;
const editableFields=['os','auto_mask','caps_swap','face','power','wheel','names','lighting','light_mode','reduced_motion','companion','screen_color','indicators','keys','colors','layer_colors','macros'];
let autoSaving=false;
let resolvedTransport=null,connectionReady=false,connectionSnapshot=null,settingsBoard=null,settingsRoute=null,detecting=false,autoReadKey=null;
function routeKey(){return JSON.stringify([connectionSnapshot?.choice.board_identity,resolvedTransport,connectionSnapshot?.choice.slot]);}
function sameSettingsRoute(){return !settingsRoute||settingsRoute===routeKey();}
function connectionFields(action){return {transport:$('#settings-transport').value,expected_transport:resolvedTransport,expected_slot:connectionSnapshot?.choice.slot,board_identity:action==='read'?connectionSnapshot?.choice.board_identity:settingsBoard||connectionSnapshot?.choice.board_identity};}
async function refreshConnection(){
 if(busy||detecting||document.hidden)return;
 const mode=$('#settings-transport').value;detecting=true;updateButtons();
 try{
  const response=await fetch('/api/hardware',{method:'POST',headers:{'Content-Type':'application/json','X-F75-CSRF':csrf},body:JSON.stringify({action:'connections',transport:mode})});
  const snapshot=await response.json();if(!response.ok)throw Error(snapshot.error||'Connection check failed');
  if($('#settings-transport').value!==mode)return;
  connectionSnapshot=snapshot;resolvedTransport=snapshot.choice.selected;connectionReady=snapshot.choice.ready;
  bluetoothAccess=snapshot.bluetooth.access;
  const label=resolvedTransport==='bluetooth'?'Bluetooth · BT'+snapshot.choice.slot:resolvedTransport==='usb'?'USB':null;
  $('#settings-transport option[value="auto"]').textContent=mode==='auto'&&label?'Automatic · '+label:'Automatic';
  $('#connection-state').textContent=connectionReady?'Connected':snapshot.choice.reason||'Disconnected';
  $('#connection-intro').textContent=label?'F75 Max · '+label:'Connect your keyboard to load its settings.';
  document.body.dataset.connected=String(connectionReady);
  if(dirty&&!sameSettingsRoute()){$('#state-label').textContent='Waiting for keyboard';$('#message').textContent='Your edits are kept here. Reconnect the original keyboard and slot, or Reload to start over.';}
  $('#bluetooth-access').hidden=resolvedTransport!=='bluetooth'||bluetoothAccess==='granted';
  displayReady=connectionReady;
  if(!resolvedTransport)autoReadKey=null;
 }catch(error){connectionReady=displayReady=false;resolvedTransport=null;$('#connection-state').textContent=error.message;}
 finally{detecting=false;updateButtons();if($('#settings-transport').value!==mode)queueMicrotask(refreshConnection);}
 const key=connectionSnapshot?.choice.board_identity+':'+resolvedTransport+':'+connectionSnapshot?.choice.slot;
 if(connectionReady&&!settings&&!dirty&&autoReadKey!==key){autoReadKey=key;await send('read');}
}

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
 document.title=current.textContent+' — F75 Studio';
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

// One small, consistent outline icon family; labels remain the accessible names.
const navPaths={keys:'M3 5h18v14H3z M6 9h1m3 0h1m3 0h1m3 0h0 M6 12h1m3 0h1m3 0h1m3 0h0 M7 16h10',lighting:'M12 3v2m0 14v2M3 12h2m14 0h2M5.6 5.6 7 7m10 10 1.4 1.4M5.6 18.4 7 17M17 7l1.4-1.4 M16 12a4 4 0 1 1-8 0 4 4 0 0 1 8 0',devices:'M10 3l8 6-12 8m4 4 8-6L6 7m4-4v18',screen:'M3 4h18v13H3z M8 21h8m-4-4v4',macros:'M8 4v16l12-8z',status:'M5 17h14l-2-3V9a5 5 0 0 0-10 0v5z M10 21h4'};
for(const link of document.querySelectorAll('[data-section]')){
 const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');svg.setAttribute('viewBox','0 0 24 24');svg.setAttribute('class','nav-icon');svg.setAttribute('aria-hidden','true');
 const path=document.createElementNS(svg.namespaceURI,'path');path.setAttribute('d',navPaths[link.dataset.section]);svg.append(path);link.prepend(svg);
}
window.F75Studio={navigate:section=>showSection(section,true),reload:()=>send('read'),clock:()=>send('clock')};
window.addEventListener('pywebviewready',()=>window.pywebview.api.set_pending(dirty));

const reserved=new Set([0,7,13,19,25,31,41,52,62,71,84]);
const names={224:'Left Ctrl',225:'Left Shift',226:'Left Alt / Option',227:'Left Command / Windows',228:'Right Ctrl',229:'Right Shift',230:'Right Alt / Option',231:'Right Command / Windows',256:'Primary (Cmd / Ctrl)'};
const logicalKeys=()=>[...new Map(F75_LAYOUT.filter(k=>k.label!=='Fn').map(k=>[k.usage,names[k.usage]||k.label])).entries()].concat([[228,'Right Ctrl'],[231,'Right Command / Windows']]);
function option(select,value,label){const o=document.createElement('option');o.value=value;o.textContent=label;select.append(o);}
function validationMessage(){
 if($('#editor input:invalid'))return 'Finish the highlighted field to save.';
 if(settings?.names.some(name=>!name.trim()||!/^[\x20-\x7e]{1,18}$/.test(name)))return 'Device names need 1–18 plain letters, numbers or punctuation.';
 if(!settings)return null;
 for(const keys of settings.keys)for(const usage of keys)if(usage>=0x8000&&usage<0x8008&&!settings.macros[usage-0x8000].steps.length)return 'Add steps to Macro '+(usage-0x8000+1)+' before it saves.';
 for(const [index,macro] of settings.macros.entries())for(const primary of [224,227]){
  const held=new Set();let duration=0;
  for(const step of macro.steps){
   duration+=step.delay_ms;if(duration>120000)return 'Macro '+(index+1)+' must stay under two minutes.';
   if(!step.usage)continue;
   const key=(step.usage&0x7fff)===256?primary:step.usage&0x7fff;
   if(step.usage&0x8000){if(!held.has(key))return 'Macro '+(index+1)+': add a press before each release.';held.delete(key);}
   else{if(held.has(key))return 'Macro '+(index+1)+': release each key before pressing it again.';held.add(key);}
   if([...held].filter(key=>key<224).length>6)return 'A macro can hold up to six ordinary keys.';
  }
  if(held.size)return 'Macro '+(index+1)+': add a release for every press to save.';
 }
 return null;
}
const autoSave=new F75AutoSave({
 document:()=>settings,
 signature:document=>JSON.stringify(editableFields.map(key=>document[key])),
 busy:()=>busy||detecting||!connectionReady||!settings||!sameSettingsRoute(),
 validate:validationMessage,
 write:async snapshot=>{
  const fields=connectionFields('save');
  const operation_id=transferProgress.start('save',resolvedTransport,csrf);
  busy=autoSaving=true;updateButtons();
  try{
   const response=await fetch('/api/hardware',{method:'POST',headers:{'Content-Type':'application/json','X-F75-CSRF':csrf},body:JSON.stringify({action:'save',operation_id,document:snapshot,...fields})});
   const result=await response.json();if(!response.ok)throw Error(result.error||'Save was not confirmed.');
   transferProgress.finish(true);return result;
  }catch(error){transferProgress.finish(false);throw error;}
  finally{busy=autoSaving=false;updateButtons();}
 },
 accept:(result,newerEdits)=>{
  // Keep live control references and newer values; advance only verified metadata.
  const pending=Object.fromEntries(editableFields.map(key=>[key,settings[key]]));
  settings={...result.document,...pending};observedHost=result.host_status;settingsBoard=result.board_identity;
 },
 state:(state,error)=>{
  dirty=autoSave.pending;
  window.pywebview?.api.set_pending(dirty);
  document.body.dataset.saveState=state;
  $('#state-label').textContent={ready:'Ready',waiting:'Changes waiting',saving:'Saving…',saved:'All changes saved',invalid:'Finish editing',error:'Not saved'}[state];
  $('#retry-save').hidden=state!=='error';
  $('#message').textContent=error||{waiting:'Changes save after you pause.',saving:'Saving to your keyboard. You can keep editing.',saved:''}[state]||'';
  if(state==='saved'||state==='ready')setTimeout(()=>{if(!dirty&&!busy)transferProgress.dismiss();},1500);
  updateButtons();
 }
});
function mark(){if(!busy)transferProgress.dismiss();autoSave.edited();updateButtons();paint();}
function updateButtons(){
 const ready=connectionReady&&!detecting;const sameBoard=sameSettingsRoute();
 $('#editor').disabled=(busy&&!autoSaving)||!settings;$('#read').disabled=busy||!ready;
 $('#read').textContent='Reload';
 $('#read').title=dirty?'Reload from the keyboard and discard unsaved edits':'Reload keyboard settings (⌘R)';
 $('#retry-save').disabled=busy||!ready||!sameBoard;
 $('#display-send').disabled=busy||!ready||!displayReady;
 $('#display-clear').disabled=busy||!ready||!displayReady;
 $('#display-transport').disabled=busy;
 $('#display-check').disabled=busy;
 // A pending draft stays bound to its keyboard and transport until saved or reloaded.
 $('#settings-transport').disabled=busy||dirty;
 $('#bluetooth-allow').disabled=busy;$('#bluetooth-recheck').disabled=busy;
 $('#settings-connection-note').hidden=true;
 const clockSupported=resolvedTransport==='usb'||!!settings?.bluetooth_clock_supported;
 $('#sync-clock').disabled=busy||!ready||!sameBoard||!settings||!clockSupported;
 $('#sync-clock').title=resolvedTransport==='bluetooth'&&!clockSupported?'Update the keyboard firmware for Bluetooth clock sync.':'';
}
async function checkBluetoothAccess(request=false){
 if(busy)return;busy=true;updateButtons();
 try{
  const response=await fetch('/api/hardware',{method:'POST',headers:{'Content-Type':'application/json','X-F75-CSRF':csrf},body:JSON.stringify({action:request?'bluetooth-request-access':'bluetooth-access'})});
  const result=await response.json();if(!response.ok)throw Error(result.error||'Could not check permission.');
  bluetoothAccess=result.access;$('#bluetooth-access').hidden=result.access==='granted';
  $('#bluetooth-access-message').textContent=result.access==='granted'?'Bluetooth access is ready.':'Mac Input Monitoring lets Studio exchange settings with this Bluetooth keyboard. Studio does not record key codes or typed text. Enable F75 Studio in System Settings > Privacy & Security > Input Monitoring, then quit and reopen Studio.';
 }catch(error){$('#bluetooth-access').hidden=false;$('#bluetooth-access-message').textContent=error.message;}
 finally{busy=false;updateButtons();await refreshConnection();}
}
$('#bluetooth-allow').onclick=()=>checkBluetoothAccess(true);
$('#bluetooth-recheck').onclick=()=>checkBluetoothAccess();
async function send(action){
 if(busy||!connectionReady||detecting)return;
 if(action==='read'&&dirty){
  if(!window.confirm('Reload from the keyboard and discard changes that have not saved?'))return;
  autoSave.paused=true;clearTimeout(autoSave.timer);
 }
 const fields=connectionFields(action);
 const operation_id=transferProgress.start(action,resolvedTransport,csrf);
 busy=true;updateButtons();$('#message').textContent=action==='clock'?'Synchronizing clock…':'Loading keyboard settings…';
 try{
  const time=new Date();const seconds=time.getHours()*3600+time.getMinutes()*60+time.getSeconds();
  const response=await fetch('/api/hardware',{method:'POST',headers:{'Content-Type':'application/json','X-F75-CSRF':csrf},body:JSON.stringify({action,operation_id,seconds,...fields})});
  const result=await response.json();if(!response.ok)throw Error(result.error||'Keyboard request failed');
  if(action==='clock'){transferProgress.finish(true);$('#message').textContent='Clock synchronized.';return;}
  settings=result.document;observedHost=result.host_status;settingsBoard=result.board_identity;settingsRoute=routeKey();autoSave.loaded();
  render();transferProgress.finish(true);
 }catch(error){transferProgress.finish(false);$('#message').textContent=error.message;$('#state-label').textContent=dirty?'Changes kept in Studio':'Settings unavailable';}
 finally{busy=false;updateButtons();if(desktop&&action==='read')await refreshDisplay();}
}
async function displayRequest(action, fields={}) {
 const response=await fetch('/api/hardware',{
  method:'POST', headers:{'Content-Type':'application/json','X-F75-CSRF':csrf},
  body:JSON.stringify({action:'display-'+action,...connectionFields('display'),...fields})
 });
 const result=await response.json();
 if(!response.ok) throw Error(result.error || 'Keyboard display request failed');
 return result;
}
function displayAvailability(result) {
 displayReady=result.ready;
 if(result.transport==='bluetooth') return 'Bluetooth ready. Show a message on the keyboard’s Home screen.';
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
 const indicators=settings.indicators||{caps:true,fn:true,caps_color:'#a8ead4',fn_color:'#c8aaf6',custom:false};
 $('#caps-light').checked=indicators.caps;$('#fn-light').checked=indicators.fn;
 for(const [name,id] of [['caps_color','caps-light'],['fn_color','fn-light']]){$('#'+id+'-color').value=indicators[name];$('#'+id+'-hex').value=indicators[name].toUpperCase();}
 $('#indicator-controls').disabled=!settings.indicator_supported;$('#indicator-support').textContent=settings.indicator_supported?'':'Update keyboard firmware to customize these indicators.';
 $('#main-color').value=settings.lighting.color;$('#light-effect').value=String(settings.lighting.effect);
 for(const [name,id] of [['brightness','light-brightness'],['speed','light-speed']]){$('#'+id).value=settings.lighting[name];$('#'+name+'-value').textContent=settings.lighting[name]+'%';}
 $('#quiet-motion').checked=settings.reduced_motion;$('#screen-theme').value=settings.light_mode?'1':'0';$('#screen-accent').value=settings.screen_color||'#91e2ce';
 $('#main-color-hex').value=settings.lighting.color.toUpperCase();$('#screen-accent-hex').value=settings.screen_color?.toUpperCase()||'';
 for(const id of ['main-color-hex','screen-accent-hex','caps-light-hex','fn-light-hex']){$('#'+id).setCustomValidity('');$('#'+id).setAttribute('aria-invalid','false');$('#'+id+'-error').textContent='';}
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
  else{autoSave.schedule();updateButtons();}
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
$('#read').onclick=()=>send('read');$('#retry-save').onclick=()=>autoSave.retry();
window.addEventListener('keydown',event=>{if((event.metaKey||event.ctrlKey)&&event.key.toLowerCase()==='r'){event.preventDefault();send('read');}});
$('#layer').onchange=()=>{layer=Number($('#layer').value);if(settings)selection();};
$('#binding').onchange=()=>{settings.keys[layer][chosen.matrix]=Number($('#binding').value);mark();};
$('#paint-key').onclick=()=>{if(chosen){settings.colors[layer][chosen.matrix]=$('#paint').value;mark();}};
$('#inherit-key').onclick=()=>{if(chosen){settings.colors[layer][chosen.matrix]=null;mark();}};
$('#paint-layer').onclick=()=>{settings.layer_colors[layer]=$('#paint').value;mark();};$('#inherit-layer').onclick=()=>{settings.layer_colors[layer]=null;mark();};
$('#caps').onchange=()=>{settings.caps_swap=$('#caps').checked;mark();};
$('#companion').onchange=()=>{settings.companion=Number($('#companion').value);mark();};
$('#wheel-mode').onchange=()=>{settings.wheel=Number($('#wheel-mode').value);mark();};
$('#power-mode').onchange=()=>{settings.power=Number($('#power-mode').value);mark();};
for(const [id,name] of [['caps-light','caps'],['fn-light','fn']])$('#'+id).onchange=()=>{settings.indicators[name]=$('#'+id).checked;settings.indicators.custom=true;mark();};
for(const [id,name] of [['caps-light','caps_color'],['fn-light','fn_color']])colorInput(id+'-color',id+'-hex',value=>{settings.indicators[name]=value;settings.indicators.custom=true;});
$('#display-send').onclick=()=>sendDisplay('set');
$('#display-clear').onclick=()=>sendDisplay('clear');
$('#display-transport').onchange=async()=>{$('#settings-transport').value=$('#display-transport').value;await refreshConnection();};
$('#settings-transport').onchange=async()=>{$('#display-transport').value=$('#settings-transport').value;connectionReady=displayReady=false;await refreshConnection();};
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
  $('#settings-transport option[value="bluetooth"]').disabled=data.bluetooth_settings!==true;
  if(desktop){
   document.body.classList.add('desktop');
   $('#desktop-sections').hidden=false;
   document.querySelector('[data-section="status"]').hidden=false;
   $('#display-connection').hidden=true;
   $('#settings-connection').hidden=false;
   $('#settings-transport option[value="bluetooth"]').disabled=data.bluetooth_settings!==true;
  }
  showSection(document.querySelector(`[data-section][href="${location.hash}"]`)?.dataset.section||'keys');
  for(const key of F75_LAYOUT){const b=document.createElement('button');b.className='key';b.dataset.key=key.id;b.textContent=key.label;b.setAttribute('aria-label','Select '+key.label);b.setAttribute('aria-pressed','false');
   Object.assign(b.style,{left:key.x/660*100+'%',top:key.y/280*100+'%',width:key.w/660*100+'%',height:key.h/280*100+'%'});
   b.onclick=()=>{chosen=layout.find(x=>String(x.key_index)===key.id);selection();};$('#keyboard').append(b);
  }
  $('#settings-connection').hidden=false;
  await refreshConnection();
  const poll=setInterval(refreshConnection,4000);window.addEventListener('pagehide',()=>clearInterval(poll),{once:true});
  document.addEventListener('visibilitychange',()=>{if(!document.hidden)refreshConnection();});
 }catch(error){$('#message').textContent=error.message;$('#read').disabled=true;}
})();
