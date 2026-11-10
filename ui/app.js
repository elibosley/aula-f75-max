/* Interactive design prototype. This module has no HID, Bluetooth, or flashing transport. */
'use strict';
const $ = s => document.querySelector(s);
const STORAGE = 'f75-studio-profile-v1';
let engine;
let startupMessage = '';
try { const saved = localStorage.getItem(STORAGE); engine = new F75.Engine(saved ? F75.deserialize(saved) : F75.defaults()); }
catch (_) { engine = new F75.Engine(); startupMessage = 'Saved profile was invalid. Defaults restored; import a known profile to recover.'; }
let tab = 'Pet'; let selected = new Set(); let holdTimer; let holdStarted;
let petDemoTimer=null;
const petAtlas=new Image();petAtlas.src='assets/chibi-sprites.png';petAtlas.onload=()=>paint();
const motionQuery = matchMedia('(prefers-reduced-motion: reduce)');
const screen = $('#screen'); const context = screen.getContext('2d');
const guide = { '1':'DEVICES','2':'KEYS','3':'LIGHTS','4':'POWER','5':'FOCUS','↑':'UP','↓':'DOWN','←':'BACK','→':'NEXT','Enter':'SELECT','Esc':'BACK','S':'SAVE','M':'OS' };
const escapeHTML = value => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const hostLabel = id => id === 'rf' ? '2.4G' : id.toUpperCase();
const osLabel = os => os === 'mac' ? 'Mac' : os === 'android' ? 'Android' : 'Windows';
const live = message => { $('#message').textContent = message; };
function act(callback, full = true) { callback(); if (full) render(); else paint(); }
function switchHost(id) { act(() => engine.switchHost(id)); }
function setOS(os) { act(() => engine.setOS(os)); }
function setCaps() { act(() => engine.toggleCaps($('#caps-swap').checked)); }
function recordPetTaps(count=1){window.F75_NATIVE?.petTaps(count);}
function stopPetDemo(){if(petDemoTimer)clearInterval(petDemoTimer);petDemoTimer=null;updatePet();}
function updatePet(){
  const p=window.F75_PET;
  if($('#pet-pace'))$('#pet-pace').textContent=p?'~'+p.wpm+' WPM':'—';
  if($('#pet-mood'))$('#pet-mood').textContent=p?p.mode:'Ready';
  if($('#pet-reaction'))$('#pet-reaction').textContent=p?.effect&&p.effect!=='None'?p.effect:p?.quiet?'Quiet mode':({Idle:'Ready when you are',Typing:'Typing along',Flow:'In the zone',Zoom:'Look at you go',Sleepy:'A little nap'})[p?.mode]||'Ready when you are';
  if($('#pet-demo')){$('#pet-demo').textContent=petDemoTimer?'Stop demo':'Try a typing burst';$('#pet-demo').disabled=!window.F75_NATIVE?.connected;}
}
function updateFocus(){
  const t=window.F75_TIMER;if(!t)return;
  const remaining=$('#focus-remaining');if(remaining)remaining.textContent=String(Math.floor(t.remaining/60)).padStart(2,'0')+':'+String(t.remaining%60).padStart(2,'0');
  const phase=$('#focus-phase');if(phase)phase.textContent=t.phase;
  const status=$('#focus-status');if(status){const message=t.alert?'Session complete. Ready for the next session.':t.running?'Running · '+t.completed+'/4 focus sessions complete':t.remaining===1500?'Ready when you are.':'Paused · '+t.completed+'/4 focus sessions complete';if(status.textContent!==message)status.textContent=message;}
  const toggle=$('#focus-toggle');if(toggle){toggle.textContent=t.running?'Pause':t.alert?'Start next session':'Start / resume';toggle.disabled=!window.F75_NATIVE?.connected;}
  for(const id of ['focus-next','focus-reset'])if($('#'+id))$('#'+id).disabled=!window.F75_NATIVE?.connected;
}
function setPage(page) { engine.page = page; engine.cursor = 0; paint(); }
function save() {
  try { localStorage.setItem(STORAGE, engine.save()); live('Profile saved in this browser. Hardware transport is not attached.'); }
  catch (_) { live('Browser storage is unavailable. Export your profile to keep these settings.'); }
  render();
}
function renderKeyboard() {
  const board = $('#keyboard'); board.replaceChildren();
  for (const key of F75_LAYOUT) {
    const b = document.createElement('button'); b.className = 'key'; b.dataset.key = key.id;
    if (key.usage >= 0xe0 || key.label === 'Fn' || key.label === 'CapsLock') b.classList.add('modifier');
    if (key.label === 'Esc' || key.label === 'Enter') b.classList.add('accent');
    Object.assign(b.style, {left:key.x / 660 * 100 + '%', top:key.y / 280 * 100 + '%', width:key.w / 660 * 100 + '%', height:key.h / 280 * 100 + '%'});
    b.setAttribute('aria-label', 'Key ' + key.label); b.setAttribute('aria-pressed','false');
    b.addEventListener('click', () => {
      if (engine.control) {
        const name = key.usage >= 0x1e && key.usage <= 0x22 ? String(key.usage - 0x1d) : ({'↑':'ArrowUp','↓':'ArrowDown','←':'ArrowLeft','→':'ArrowRight','Esc':'Escape'})[key.label] || key.label.toLowerCase();
        engine.controlKey(name === 'enter' ? 'Enter' : name); render();
      } else {
        if(engine.page==='Home'&&key.usage>=4&&key.usage<=0x38)recordPetTaps();
        if (selected.has(key.id)) selected.delete(key.id); else selected.add(key.id);
        if (tab === 'Keys') {
          const usage = engine.keyDown(key.id,key.usage); engine.keyUp(key.id);
          $('#key-result').textContent = key.label + ' sends ' + usageName(usage);
        } else { $('#key-result').textContent = selected.size + ' key' + (selected.size === 1 ? '' : 's') + ' selected'; }
        updateKeys(); if (tab === 'Lighting') renderInspector();
      }
    });
    board.appendChild(b);
  }
}
function usageName(usage) { return ({57:'Caps Lock',224:'Ctrl',226:'Option / Alt',227:'Command / Windows',230:'Right Option / Alt',231:'Right Command / Windows'})[usage] || 'HID 0x' + Number(usage || 0).toString(16); }
function shortLabel(key) {
  if (engine.control && guide[key.label.replace(/[^1-5]/g,'')] && /^[!@#$%]?[1-5]$/.test(key.label)) return guide[key.label.replace(/[^1-5]/g,'')];
  if (engine.control && guide[key.label]) return guide[key.label];
  if (key.usage === 0x39) return engine.config.capsSwap ? (engine.host().os === 'mac' ? 'Cmd' : 'Ctrl') : 'Caps';
  if (key.usage === 0xe0) return engine.config.capsSwap ? 'Caps' : (engine.host().os === 'mac' ? 'Cmd' : 'Ctrl');
  if (engine.host().os === 'mac' && [0xe2,0xe6].includes(key.usage)) return 'Cmd';
  if (engine.host().os === 'mac' && [0xe3,0xe7].includes(key.usage)) return 'Opt';
  const labels = {'Shift_L':'Shift','Shift_R':'Shift','Ctrl_L':'Ctrl','Win_L':'Win','Alt_L':'Alt','Alt_R':'Alt','CapsLock':'Caps','Backspace':'Back','delete':'Del','page up':'PgUp','page down':'PgDn','end':'End','Space':'','~`':'`','|\\':'\\','}}':']'};
  return labels[key.label] ?? key.label;
}
function updateKeys() {
  const reduced = engine.config.reducedMotion || motionQuery.matches;
  const budget = engine.powerState();
  for (const key of F75_LAYOUT) {
    const el = document.querySelector(`[data-key="${key.id}"]`); const label = shortLabel(key);
    el.textContent = label; el.classList.toggle('selected',selected.has(key.id));
    const isGuide = engine.control && (Object.values(guide).includes(label)); el.classList.toggle('guide',isGuide);
    el.setAttribute('aria-pressed',String(selected.has(key.id)));
    const base = engine.config.lighting.perKey[key.id] || (engine.layer() === 'Base' ? engine.config.lighting.color : engine.config.layerColors[engine.layer()]);
    el.style.setProperty('--key-color',base);
    let level = budget.rgb / 100;
    const speed = .0001 + engine.config.lighting.speed * .000018;
    const phase = engine.time * speed;
    if (!reduced && budget.fps) {
      if (engine.config.lighting.effect === 'Tidal') level *= .4 + .6 * (Math.sin(phase - key.x / 100) + 1) / 2;
      if (engine.config.lighting.effect === 'Rain') level *= Math.sin(phase * 2 + Number(key.id) * 3) > .85 ? 1 : .12;
      if (engine.config.lighting.effect === 'Trails') level *= Math.max(.12,Math.cos(phase - key.x / 80));
      if (engine.config.lighting.effect === 'Constellation') level *= .2 + .8 * Math.pow((Math.sin(phase / 2 + Number(key.id)) + 1) / 2,6);
    }
    el.style.setProperty('--glow',Math.min(1,level * 2.5));
  }
  $('#layer-indicator').textContent = engine.layer().toUpperCase() + ' LAYER';
  $('#control').setAttribute('aria-pressed',String(engine.control));
  $('#function').setAttribute('aria-pressed',String(engine.functionLayer));
}
function renderInspector() {
  const c = engine.config; const h = engine.host(); let html = '';
  if(tab!=='Pet'&&petDemoTimer)stopPetDemo();
  if(tab==='Pet'){
    html=`<h2>A little company.</h2><p class="description">A quiet desk companion who types along with you. Faster bursts bring little surprises.</p><label class="field"><span>Home screen</span><select id="screen-face">${['Chibi','Orbit','Minimal','Constellation'].map(n=>`<option ${c.screenFace===n?'selected':''}>${n}</option>`).join('')}</select></label><label class="color-line">Screen accent<input id="preview-accent" type="color" value="${c.screenColor||'#91e2ce'}"></label><button id="preview-accent-default" class="text-button">Default accent</button><label class="field"><span>Try typing here</span><input id="pet-type" type="text" autocomplete="off" autocapitalize="off" spellcheck="false" placeholder="A little hello…"></label><div class="metrics"><div class="metric">Recent typing pace<b id="pet-pace">—</b>Four-second estimate</div><div class="metric">Mood<b id="pet-mood">Ready</b><span id="pet-reaction">Waiting for a typing burst</span></div></div><button id="pet-demo" class="wide primary" disabled>Try a typing burst</button><p class="note">Only tap counts reach the animation. Text in this box stays in your browser and is not saved. Pasting does not boost her pace.</p><p class="note">Low battery and reduced motion keep her still. Focus alerts take priority.</p>`;
  }
  if (tab === 'Devices') {
    html = '<h2>A place for every device.</h2><p class="description">A remembered layout for each connection. Switching devices brings its Mac or Windows profile with it.</p>';
    for (const id of F75.HOSTS) {
      const item = c.hosts[id]; const active = id === c.activeHost;
      html += `<div class="host"><div class="host-top"><span class="host-id">${hostLabel(id)}</span><span class="host-name">${escapeHTML(item.name)}</span><span class="host-state">${engine.connected === id ? 'Connected' : active ? 'Connecting' : item.bonded ? osLabel(item.os) : 'Empty'}</span></div><div class="actions"><button data-connect="${id}" ${engine.pairing ? 'disabled' : ''}>${active ? 'Reconnect' : 'Switch'}</button>${id.startsWith('bt') ? `<button data-pair="${id}" ${engine.pairing ? 'disabled' : ''}>${item.bonded ? 'Replace device' : 'Pair device'}</button>` : ''}</div></div>`;
    }
    html += `<div class="device-editor"><label class="field"><span>Name for ${hostLabel(c.activeHost)}</span><input id="host-name" maxlength="18" type="text" value="${escapeHTML(h.name)}"></label><label class="field"><span>Layout for this connection</span><select id="host-os"><option value="auto" ${h.automatic?'selected':''}>Auto · ${osLabel(h.os)}</option>${['mac','windows','android'].map(os=>`<option value="${os}" ${!h.automatic&&h.os===os?'selected':''}>${osLabel(os)}</option>`).join('')}</select></label></div>`;
    if (engine.confirm) html += `<div class="callout">${engine.confirm.replacing ? 'Replace the device saved in ' : 'Pair a device in '}${hostLabel(engine.confirm.id)}? Hold to confirm.</div><button id="pair-hold" class="hold-button">Hold to pair · 1.2 seconds</button><button id="pair-cancel" class="wide">Cancel</button>`;
    if (engine.pairing) html += `<div class="callout">Pairing ${hostLabel(engine.pairing.id)}. Open Bluetooth settings on your computer.<br><span id="pair-countdown"></span></div><button id="pair-cancel" class="wide">Cancel pairing</button>`;
    if (engine.error) html += `<p class="error" role="alert">${escapeHTML(engine.error)}</p>`;
    html += '<p class="note">Bluetooth names are labels you set here. Actual radio pairing still needs a firmware adapter.</p>';
  }
  if (tab === 'Keys') {
    html = `<h2>Muscle memory, kept.</h2><p class="description">One global Caps / Ctrl swap. A separate modifier layout for each computer.</p><label class="field"><span>Layout for this connection</span><select id="host-os"><option value="auto" ${h.automatic?'selected':''}>Auto · ${osLabel(h.os)}</option>${['mac','windows','android'].map(os=>`<option value="${os}" ${!h.automatic&&h.os===os?'selected':''}>${osLabel(os)}</option>`).join('')}</select></label><label class="setting-row" for="caps-swap"><span><strong>Swap Caps and left Ctrl</strong><small>Caps becomes Command on Mac and Ctrl on Windows or Android. Left Ctrl becomes Caps Lock.</small></span><input id="caps-swap" class="switch" type="checkbox" ${c.capsSwap?'checked':''}></label><label class="field"><span>Wheel action while typing</span><select id="wheel-action">${['Volume','Scroll','Brightness'].map(n=>`<option ${c.wheel===n?'selected':''}>${n}</option>`).join('')}</select></label><label class="field"><span>Home screen</span><select id="screen-face">${['Chibi','Orbit','Minimal','Constellation'].map(n=>`<option ${c.screenFace===n?'selected':''}>${n}</option>`).join('')}</select></label><div class="callout">${h.os==='mac'?'Mac: Command at the Alt positions; Option at the Windows positions.':'Windows: the original Alt and Windows positions.'}</div><p class="note">Hold Fn + Space for board controls. Use 1–5 to open a section, arrows or J/K to move, Enter to select, Esc to go back, and S to save.</p><button id="show-controls" class="wide">Try the control layer</button>`;
  }
  if (tab === 'Lighting') {
    html = `<h2>Color with intention.</h2><p class="description">Paint individual keys, build a quiet palette, or let a subtle animation move across the board.</p><label class="field"><span>Animation</span><select id="effect">${F75.EFFECTS.map(n=>`<option ${c.lighting.effect===n?'selected':''}>${n}</option>`).join('')}</select></label><div class="range-heading"><label for="brightness">Brightness</label><output id="brightness-value">${c.lighting.brightness}%</output></div><input id="brightness" type="range" min="0" max="100" value="${c.lighting.brightness}"><div class="range-heading"><label for="speed">Movement</label><output id="speed-value">${c.lighting.speed}%</output></div><input id="speed" type="range" min="0" max="100" value="${c.lighting.speed}"><div class="swatches">${['#91e2ce','#edc08c','#c4b4ef','#f2a4aa','#a4c8f2'].map(x=>`<button class="swatch" data-color="${x}" style="--swatch:${x}" aria-label="Use color ${x}"></button>`).join('')}</div><label class="color-line">Custom color<input id="color" type="color" value="${c.lighting.color}"></label><div class="setting-row"><span><strong>${selected.size} keys selected</strong><small>Click keys on the board to select them.</small></span><button id="select-all">All keys</button></div><button id="paint-selected" class="wide" ${selected.size?'':'disabled'}>Paint selected keys</button><button id="clear-selection" class="wide" ${selected.size?'':'disabled'}>Clear selection</button><label class="setting-row"><span><strong>Reduced motion</strong><small>Still lighting and quiet screen transitions.</small></span><input id="reduced-motion" class="switch" type="checkbox" ${c.reducedMotion?'checked':''}></label><p class="note">Control and Fn layers use their own accent colors. Power profiles cap brightness while on battery.</p>`;
  }
  if (tab === 'Power') {
    html = `<h2>Predictable by default.</h2><p class="description">Consistent idle behavior and brightness limits. No guessed battery-hour estimates.</p>${Object.entries(F75.POLICIES).map(([name,p])=>`<button class="preset" data-power="${name}" aria-pressed="${c.power===name}"><strong>${name}</strong><span>${name==='Balanced'?'Everyday wireless use':name==='Endurance'?'Less light, fewer redraws':'Brighter and more animated'} · dim after ${p.dim/1000}s<br>Screen off ${p.off/1000}s · sleep ${p.sleep/60000} min</span></button>`).join('')}<div class="metrics"><div class="metric">RGB ceiling on battery<b id="rgb-budget">${engine.powerState().rgb}%</b>Current effective setting</div><div class="metric">Display updates<b id="fps-budget">${engine.powerState().fps} fps</b>Animation ceiling</div></div><div class="callout">Below 10%: dim lights and stop animations. At 5%: RGB off. Typing remains available.</div><p class="note">These policies need current-draw and wake tests on the board. Battery percentage is simulated here.</p>`;
  }
  if(tab==='Focus'){
    html='<h2>Time for one thing.</h2><p class="description">25 minutes of focus. A 5-minute break. A 15-minute break after four completed focus sessions.</p><p id="focus-phase" class="eyebrow">Focus</p><output id="focus-remaining" class="focus-time" aria-label="Time remaining">25:00</output><p id="focus-status" role="status" aria-live="polite">Ready when you are.</p><button id="focus-toggle" class="primary wide" disabled>Start / resume</button><div class="actions"><button id="focus-next" disabled>Next session</button><button id="focus-reset" disabled>Reset cycle</button></div><p class="note">Completion gives two gentle screen pulses, then a notice until dismissed. Reduced motion uses a static notice. Each session starts when you choose.</p>';
  }
  $('#inspector').innerHTML = html;
  $('#preview-accent')?.addEventListener('input',e=>act(()=>{engine.config.screenColor=e.target.value;engine.changed();}));
  $('#preview-accent-default')?.addEventListener('click',()=>act(()=>{engine.config.screenColor=null;engine.changed();}));
  $('#pet-type')?.addEventListener('beforeinput',e=>{if(!e.isComposing&&['insertText','deleteContentBackward','insertLineBreak'].includes(e.inputType))recordPetTaps();});
  $('#preview-accent')?.addEventListener('input',e=>act(()=>{engine.config.screenColor=e.target.value;engine.changed();}));
  $('#preview-accent-default')?.addEventListener('click',()=>act(()=>{engine.config.screenColor=null;engine.changed();}));
  $('#pet-type')?.addEventListener('compositionend',()=>recordPetTaps());
  $('#pet-demo')?.addEventListener('click',()=>{
    if(petDemoTimer){stopPetDemo();return;}let sent=0;const started=performance.now();
    if(engine.config.screenFace!=='Chibi'){engine.config.screenFace='Chibi';engine.changed();}
    petDemoTimer=setInterval(()=>{
      const elapsed=Math.min(4000,performance.now()-started),target=Math.floor(elapsed*12/1000);
      if(target>sent){recordPetTaps(target-sent);sent=target;}if(elapsed>=4000)stopPetDemo();
    },80);updatePet();
  });updatePet();
  for(const [id,action] of [['focus-toggle','Toggle'],['focus-next','Next'],['focus-reset','Reset']])$('#'+id)?.addEventListener('click',()=>window.F75_NATIVE?.timer(action));
  updateFocus();
  for (const b of document.querySelectorAll('[data-connect]')) b.onclick=()=>switchHost(b.dataset.connect);
  for (const b of document.querySelectorAll('[data-pair]')) b.onclick=()=>act(()=>engine.requestPair(b.dataset.pair));
  $('#host-name')?.addEventListener('change',e=>act(()=>{ const name=e.target.value.trim(); if(name){engine.host().name=name;engine.changed();} }));
  $('#host-os')?.addEventListener('change',e=>setOS(e.target.value));
  for (const b of document.querySelectorAll('[data-os]')) b.onclick=()=>setOS(b.dataset.os);
  $('#caps-swap')?.addEventListener('change',setCaps);
  $('#wheel-action')?.addEventListener('change',e=>act(()=>{engine.config.wheel=e.target.value;engine.changed();}));
  $('#screen-face')?.addEventListener('change',e=>act(()=>{engine.config.screenFace=e.target.value;engine.changed();}));
  $('#show-controls')?.addEventListener('click',()=>act(()=>engine.setControl(true)));
  for(const field of ['effect','brightness','speed','color']) $('#'+field)?.addEventListener(field==='effect'?'change':'input',e=>{
    engine.setLighting(field,field==='brightness'||field==='speed'?Number(e.target.value):e.target.value);
    if($('#'+field+'-value')) $('#'+field+'-value').textContent=e.target.value+'%'; paint();
  });
  for(const b of document.querySelectorAll('[data-color]')) b.onclick=()=>act(()=>engine.setLighting('color',b.dataset.color));
  $('#select-all')?.addEventListener('click',()=>{selected=new Set(F75_LAYOUT.map(k=>k.id));render();});
  $('#clear-selection')?.addEventListener('click',()=>{selected.clear();render();});
  $('#paint-selected')?.addEventListener('click',()=>act(()=>engine.paint([...selected],c.lighting.color)));
  $('#reduced-motion')?.addEventListener('change',e=>act(()=>{c.reducedMotion=e.target.checked;engine.changed();}));
  for(const b of document.querySelectorAll('[data-power]')) b.onclick=()=>act(()=>{c.power=b.dataset.power;engine.changed();engine.activity();});
  $('#pair-cancel')?.addEventListener('click',()=>act(()=>engine.cancelPairing()));
  const hold = $('#pair-hold');
  if(hold){
    const start=()=>{holdStarted=performance.now();hold.classList.add('holding');clearTimeout(holdTimer);holdTimer=setTimeout(()=>act(()=>engine.holdConfirm(1200)),1200);};
    const stop=()=>{clearTimeout(holdTimer);hold.classList.remove('holding');};
    hold.onpointerdown=start;hold.onpointerup=stop;hold.onpointerleave=stop;hold.onpointercancel=stop;
    hold.onkeydown=e=>{if(['Enter',' '].includes(e.key)&&!e.repeat){e.preventDefault();start();}};
    hold.onkeyup=stop;
  }
}
function fontGlyph(character,scale){const font=scale>1?F75_FONT.large:scale===0?F75_FONT.compact:F75_FONT.small;return {font,glyph:font.glyphs[character]||font.glyphs['?']};}
function textWidth(value,scale=1){return [...String(value)].reduce((width,c)=>width+fontGlyph(c,scale).glyph.advance,0);}
function text(value,x,y,color='#e7f2e5',scale=1){
  context.fillStyle=color;
  for(const character of String(value)){
    const {font,glyph:g}=fontGlyph(character,scale);
    for(let yy=0;yy<g.height;yy++)for(let xx=0;xx<g.width;xx++){
      const index=yy*g.width+xx,packed=font.data[g.offset+Math.floor(index/2)],coverage=index%2?packed&15:packed>>4;
      if(coverage){context.globalAlpha=coverage/15;context.fillRect(x+g.x+xx,y+g.y+yy,1,1);}
    }
    x+=g.advance;
  }
  context.globalAlpha=1;
}
function center(value,y,color,scale=1){text(value,Math.max(7,Math.floor((128-textWidth(value,scale))/2)),y,color,scale);}
function softRect(x,y,width,height,color){
  context.fillStyle=color;
  for(const [left,top,w,h] of [[x+3,y,width-6,1],[x+1,y+1,width-2,2],[x,y+3,width,height-6],[x+1,y+height-3,width-2,2],[x+3,y+height-1,width-6,1]])context.fillRect(left,top,w,h);
}
function deskClock(time,rose){
  const outline='#4a5d58',face='#efefde',hands='#102528',cx=18,cy=87;
  context.fillStyle=rose;[[10,72,4,1],[8,73,7,2],[23,72,4,1],[22,73,7,2]].forEach(r=>context.fillRect(...r));
  context.fillStyle=outline;[[11,99,3,3],[22,99,3,3]].forEach(r=>context.fillRect(...r));
  for(let y=75;y<100;y++)for(let x=6;x<=30;x++){
    const distance=(x-cx)**2+(y-cy)**2;if(distance>144)continue;
    context.fillStyle=distance>121?outline:distance>90?rose:face;context.fillRect(x,y,1,1);
  }
  const point=(tick,radius)=>[cx+Math.round(Math.sin(tick*Math.PI/30)*radius),cy-Math.round(Math.cos(tick*Math.PI/30)*radius)];
  context.fillStyle=outline;for(let tick=0;tick<60;tick+=5){const [x,y]=point(tick,8);context.fillRect(x,y,1,1);}
  context.strokeStyle=hands;context.lineWidth=1;
  for(const [tick,radius] of [[time.getHours()%12*5+time.getMinutes()/12,5],[time.getMinutes(),7]]){
    const [x,y]=point(tick,radius);context.beginPath();context.moveTo(cx+.5,cy+.5);context.lineTo(x+.5,y+.5);context.stroke();
  }
  context.fillStyle=rose;context.fillRect(cx,cy,1,1);
}
function drawScreen(){
  if(window.F75_NATIVE_FRAME){context.drawImage(window.F75_NATIVE_FRAME,0,0,128,128);return;}
  const p=engine.powerState();const light=engine.config.screenTheme==='Light';const accent=light?'#187540':'#a8ead4',muted=light?'#4b5d58':'#90ab99',ink=light?'#102528':'#e7f2e5';
  context.fillStyle=light?'#edf0dc':'#0c1410';context.fillRect(0,0,128,128);
  if(p.stage==='off'||p.stage==='sleep'){center(p.stage==='sleep'?'SLEEP':'DISPLAY OFF',57,muted);center('ANY KEY TO WAKE',88,muted);return;}
  if(engine.page==='Home'){text(hostLabel(engine.config.activeHost),7,7,accent);text(engine.battery+'%',95,7,p.low?'#edc08c':ink);}
  else text(engine.page,8,7,accent);
  context.fillStyle='#2b3d30';context.fillRect(7,20,114,1);
  if(engine.confirm){center(engine.confirm.replacing?'REPLACE DEVICE?':'PAIR DEVICE?',32,ink);center(hostLabel(engine.confirm.id),51,accent,2);center('HOLD ENTER',82,ink);center('1.2 SEC TO CONFIRM',96,muted);center('ESC CANCELS',114,muted);return;}
  if(engine.pairing){center('PAIRING',31,ink);center(hostLabel(engine.pairing.id),49,accent,2);center('OPEN BLUETOOTH',80,muted);center('ON YOUR COMPUTER',92,muted);center(Math.max(0,Math.ceil((engine.pairing.deadline-engine.time)/1000))+' SEC',113,accent);return;}
  if(engine.control){
    text('BOARD CONTROLS',7,29,'#c4b4ef');
    [['1 DEVICES','2 KEYS'],['3 LIGHTS','4 POWER']].forEach((row,y)=>row.forEach((s,x)=>text(s,7+x*63,46+y*15,ink)));
    text('ARROWS MOVE',7,84,muted);text('ENTER SELECT',7,96,muted);text('ESC BACK  S SAVE',7,112,muted);
    if(engine.page!=='Home')text(engine.page.slice(0,12),7,72,'#c4b4ef');return;
  }
  if(engine.page==='Home'){
    if(engine.config.screenFace==='Chibi'){
      const rose=light?'#a5527b':'#e7a2de';context.fillStyle=rose;
      [0x36,0x7f,0x7f,0x3e,0x1c,0x08].forEach((row,y)=>{for(let x=0;x<7;x++)if(row&(1<<(6-x)))context.fillRect(61+x,18+y,1,1);});
      for(const [color,rect] of [['#e7b6bd',[10,101,108,1]],['#c691a5',[8,102,112,2]],['#9c718c',[10,104,108,1]]]){context.fillStyle=color;context.fillRect(...rect);}
      deskClock(new Date(),rose);
      if(petAtlas.complete&&petAtlas.naturalWidth)context.drawImage(petAtlas,0,0,64,64,24,24,80,80);
      text('0 WPM',6,105,muted);text('Idle',121-textWidth('Idle'),105,accent);return;
    }
    const time=new Date().toLocaleTimeString('en-GB',{hour:'2-digit',minute:'2-digit'});
    center(time,34,ink,3);center(engine.host().name.slice(0,18),65,muted);
    if(engine.config.screenFace!=='Minimal'){
      const move=p.fps&&!motionQuery.matches?engine.time/1200:0;
      for(let i=0;i<13;i++){
        const x=8+i*9;const y=engine.config.screenFace==='Orbit'?84+Math.round(Math.sin(move+i*.5)*3):80+(i*13%11);
        context.fillStyle=i%3===0?accent:'#385844';context.fillRect(x,y,i%3===0?2:1,i%3===0?2:1);
      }
    }
    text(engine.host().os==='mac'?'MAC':'WIN',7,99,accent);text(engine.config.capsSwap?'CAPS <> CTRL':'CAPS NORMAL',43,99,muted);
    center(engine.notice?engine.notice.slice(0,20):engine.action?engine.action.toUpperCase()+' '+(engine.action==='Volume'?engine.volume+'%':''):'',117,ink,0);return;
  }
  const rows=engine.rows();
  const labels=engine.page==='Devices'?rows.map(id=>hostLabel(id)+' '+engine.config.hosts[id].name):rows;
  const start=0;
  labels.slice(0,5).forEach((label,index)=>{
    const selectedRow=index+start===engine.cursor;
    if(selectedRow)softRect(5,29+index*15,118,13,accent);
    text(label.slice(0,18),9,30+index*15,selectedRow?(light?'#edf0dc':'#12231b'):ink);
  });
  center(engine.notice?engine.notice.slice(0,19):'TURN / PRESS / BACK',116,muted);
}
function paint(){
  const p=engine.powerState();const name=engine.pairing?'Pairing '+hostLabel(engine.pairing.id):engine.connected===engine.config.activeHost?engine.host().name:'Connecting '+hostLabel(engine.config.activeHost);
  $('#connection-state').textContent=name+' · '+osLabel(engine.host().os);
  $('#current-page').textContent=engine.control?'Your keys take over.':engine.page==='Home'?'At a glance.':engine.page+'.';
  $('#page-description').textContent=engine.control?'Number keys open sections. Arrows move. Enter selects. Esc goes back. Release to return every key to typing.':engine.page==='Focus'?'Turn to choose start/pause, next session, or reset. Press to confirm.':engine.editing?'Turn slowly for precision. Turn faster for larger changes. Press to finish.':engine.page==='Home'?'The wheel changes '+engine.config.wheel.toLowerCase()+'. Press it for your board controls. Hold it to go back.':'Turn to move. Press to select. In Lighting, press brightness or speed to adjust it with the wheel.';
  $('#saved-state').textContent=engine.dirty?'Unsaved changes':window.F75_NATIVE?.connected?'Settings saved by native core':'Settings saved in this browser';
  $('#save').textContent=engine.dirty?'Save changes':'Save settings';
  $('#screen-theme').setAttribute('aria-pressed',String(engine.config.screenTheme==='Light'));
  $('#power-summary').textContent=engine.config.power+' · '+p.stage+' · RGB '+p.rgb+'%';
  $('#control').textContent=engine.control?'Release control layer':'Hold control layer';
  const cd=$('#pair-countdown');if(cd&&engine.pairing)cd.textContent=Math.max(0,Math.ceil((engine.pairing.deadline-engine.time)/1000))+' seconds remaining';
  if($('#rgb-budget'))$('#rgb-budget').textContent=p.rgb+'%';if($('#fps-budget'))$('#fps-budget').textContent=(motionQuery.matches?0:p.fps)+' fps';
  screen.setAttribute('aria-label',`${engine.page}. ${name}. ${osLabel(engine.host().os)} profile. Battery ${engine.battery} percent. ${engine.config.capsSwap?'Caps and physical left Ctrl swapped.':''} ${engine.confirm?'Hold to confirm pairing.':engine.pairing?'Waiting for pairing.':''}`);
  drawScreen();updateKeys();
}
function render(){
  for(const b of document.querySelectorAll('[data-tab]'))b.setAttribute('aria-selected',String(b.dataset.tab===tab));
  renderInspector();paint();
}
for(const b of document.querySelectorAll('[data-tab]'))b.onclick=()=>{tab=b.dataset.tab;engine.page=tab==='Pet'?'Home':tab;engine.cursor=0;engine.editing=false;window.F75_NATIVE?.openPage(engine.page);render();};
for(const b of document.querySelectorAll('[data-jump]'))b.onclick=()=>{tab=b.dataset.jump;engine.page=tab==='Pet'?'Home':tab;engine.cursor=0;engine.editing=false;window.F75_NATIVE?.openPage(engine.page);render();document.querySelector('aside').scrollIntoView({behavior:motionQuery.matches||engine.config.reducedMotion?'instant':'smooth',block:'start'});};
$('#wheel-up').onclick=()=>act(()=>engine.turn(1));$('#wheel-down').onclick=()=>act(()=>engine.turn(-1));
$('#wheel-press').onclick=()=>act(()=>engine.press());$('#back').onclick=()=>act(()=>engine.back());
$('#screen-theme').onclick=()=>act(()=>{engine.config.screenTheme=engine.config.screenTheme==='Light'?'Dark':'Light';engine.changed();engine.activity();});
$('#wheel-feel').onchange=e=>{engine.wheelDivisor=Number(e.target.value);engine.wheelPending=0;window.F75_NATIVE?.wheelFeel(engine.wheelDivisor);};
let wheelRemainder=0,wheelLast=0;
$('#wheel-press').addEventListener('wheel',e=>{
  e.preventDefault();const now=performance.now();if(now-wheelLast>180)wheelRemainder=0;wheelLast=now;
  const delta=e.deltaY*(e.deltaMode===1?100/3:e.deltaMode===2?100:1);
  if(Math.sign(delta)!==Math.sign(wheelRemainder))wheelRemainder=0;
  wheelRemainder+=delta;const ticks=Math.trunc(wheelRemainder/100);wheelRemainder-=ticks*100;
  for(let i=0;i<Math.min(8,Math.abs(ticks));i++)engine.turn(Math.sign(ticks));
  if(ticks)render();
},{passive:false});
$('#control').onclick=()=>act(()=>engine.setControl(!engine.control));
$('#function').onclick=()=>act(()=>{engine.functionLayer=!engine.functionLayer;engine.activity();});
$('#save').onclick=save;$('#restart').onclick=()=>act(()=>{stopPetDemo();engine.reboot();live('Simulated restart. Saved Caps swap, device layouts, and lighting restored.');});
$('#size-toggle').onclick=()=>{const actual=$('.display-side').classList.toggle('actual');$('#size-toggle').setAttribute('aria-pressed',String(actual));$('#size-toggle').textContent=actual?'Enlarge':'View 1:1';};
$('#battery').oninput=e=>{engine.battery=Number(e.target.value);$('#battery-value').textContent=e.target.value+'%';paint();};
$('#charging').onchange=e=>act(()=>{engine.charging=e.target.checked;});
$('#host-connect').onclick=()=>act(()=>{const id=engine.pairing?.id||engine.config.activeHost;engine.connectedEvent(id);});
$('#idle').onclick=()=>act(()=>engine.tick(60000));$('#wake').onclick=()=>act(()=>engine.activity());
$('#timer-demo').onclick=()=>{if(!window.F75_NATIVE?.connected){live('Connect to the native preview to try the timer.');return;}window.F75_NATIVE.timer('Demo');live('Simulated elapsed time. Timer completion still comes from the C clock.');};
$('#export').onclick=()=>{const blob=new Blob([F75.serialize(engine.config)],{type:'application/json'});const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='f75-profile.json';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);live('Profile exported.');};
$('#import').onchange=async e=>{const file=e.target.files[0];if(!file)return;try{if(file.size>100000)throw Error('Profile file is too large');const config=F75.deserialize(await file.text());engine.releaseKeys();engine=new F75.Engine(config);window.F75_NATIVE?.adoptProfile(config);localStorage.setItem(STORAGE,engine.saved);live('Profile imported and saved in this browser.');render();}catch(error){live('Import failed: '+error.message);}e.target.value='';};
document.addEventListener('keydown',e=>{
  engine.activity();
  if(!engine.control&&!e.repeat&&!e.metaKey&&!e.ctrlKey&&!e.altKey&&!(e.code==='Space'&&e.shiftKey)&&!['INPUT','SELECT','TEXTAREA'].includes(document.activeElement.tagName)&&(e.key.length===1||['Backspace','Enter'].includes(e.key)))recordPetTaps();
  if(['INPUT','SELECT','TEXTAREA'].includes(document.activeElement.tagName))return;
  if(e.repeat)return;
  if(e.code==='Space'&&e.shiftKey){e.preventDefault();engine.setControl(true);render();return;}
  if(engine.control){e.preventDefault();engine.controlKey(e.key);render();}
});
document.addEventListener('keyup',e=>{if(e.code==='Space'&&engine.control){engine.setControl(false);render();}});
window.addEventListener('blur',()=>{if(engine.control){engine.setControl(false);render();}engine.releaseKeys();});
document.addEventListener('visibilitychange',()=>{if(document.hidden)stopPetDemo();});
document.addEventListener('pointerdown',()=>engine.activity(),true);
renderKeyboard();render();if(startupMessage)live(startupMessage);
let previous=performance.now(),lastPaint=0,priorPairing=false;
function frame(now){
  const delta=Math.min(1000,now-previous);previous=now;engine.tick(delta);
  const budget=engine.powerState();const fps=motionQuery.matches?0:budget.fps;
  if(now-lastPaint>1000/(fps||1)){paint();lastPaint=now;}
  if(priorPairing&&!engine.pairing)renderInspector();priorPairing=Boolean(engine.pairing);
  requestAnimationFrame(frame);
}
requestAnimationFrame(frame);
window.F75_PREVIEW={get engine(){return engine;}};
