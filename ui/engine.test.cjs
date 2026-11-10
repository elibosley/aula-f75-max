const {test} = require('node:test');
const assert = require('node:assert/strict');
const {Engine,defaults,serialize,deserialize} = require('./engine.js');
test('physical Ctrl swap stays independent of Mac/Windows modifiers',()=>{
  const e=new Engine();
  for(const os of ['mac','windows','android']){e.setOS(os);assert.equal(e.mapUsage(0x39),os==='mac'?0xe3:0xe0);assert.equal(e.mapUsage(0xe0),0x39);assert.equal(e.mapUsage(0xe4),os==='mac'?0xe7:0xe4);}
  e.setOS('mac');assert.equal(e.mapUsage(0xe2),0xe3);assert.equal(e.mapUsage(0xe3),0xe2);
  e.setOS('windows');assert.equal(e.mapUsage(0xe2),0xe2);
});
test('changing layout releases held keys with their original emitted usages',()=>{
  const e=new Engine();e.keyDown('caps',0x39);e.toggleCaps(false);e.keyUp('caps');
  assert.deepEqual(e.effects.filter(x=>x.type==='keyUp'),[{type:'keyUp',physical:'caps',usage:0xe3}]);
});
test('OS belongs to host; global swap survives profile changes and restart',()=>{
  const e=new Engine();e.setOS('windows');e.switchHost('bt1');assert.equal(e.host().os,'mac');
  assert.equal(e.connected,null);e.connectedEvent('bt1');e.save();e.reboot();
  assert.equal(e.config.capsSwap,true);assert.equal(e.config.hosts.usb.os,'windows');assert.equal(e.host().os,'mac');assert.equal(e.connected,null);
});
test('pairing requires confirmation and transport acknowledgement',()=>{
  const e=new Engine();e.requestPair('bt2');assert.equal(e.holdConfirm(1199),false);assert.equal(e.pairing,null);
  assert.equal(e.holdConfirm(1200),true);assert.equal(e.config.hosts.bt2.bonded,false);
  assert.equal(e.connectedEvent('bt3'),false);assert.equal(e.connectedEvent('bt2'),true);
  assert.equal(e.config.hosts.bt2.bonded,true);assert.equal(e.config.activeHost,'bt2');
});
test('timeout and cancel preserve saved configuration and do not report success',()=>{
  const e=new Engine();e.requestPair('bt1');e.holdConfirm(1200);e.tick(30001);
  assert.equal(e.pairing,null);assert.match(e.error,/No host/);assert.equal(e.config.activeHost,'usb');assert.equal(e.config.hosts.bt1.bonded,true);
  assert.equal(e.connectedEvent('bt1'),false);e.requestPair('bt2');e.cancelPairing();assert.equal(e.holdConfirm(1200),false);
});
test('control layer consumes navigation keys and releases typed keys on entry',()=>{
  const e=new Engine();e.keyDown('x',0x1b);e.setControl(true);e.keyDown('1',0x1e);assert.equal(e.page,'Devices');
  e.keyDown('ArrowDown',0x51);assert.equal(e.cursor,1);e.setControl(false);assert.equal(e.keysDown.size,0);
  assert.equal(e.effects.filter(x=>x.type==='keyDown').length,1);
});
test('power never changes key mapping; low battery stops animation and critical turns RGB off',()=>{
  const e=new Engine();e.battery=9;assert.equal(e.powerState().fps,0);assert.ok(e.powerState().rgb<=8);
  e.battery=5;assert.equal(e.powerState().rgb,0);assert.equal(e.mapUsage(0x39),0xe3);
  e.tick(60000);assert.equal(e.powerState().stage,'off');e.tick(130000);assert.equal(e.powerState().stage,'sleep');
  e.activity();assert.equal(e.powerState().stage,'active');
});
test('pairing suppresses idle sleep and reduced motion stops animation',()=>{
  const e=new Engine();e.config.power='Endurance';e.tick(85000);e.requestPair('bt2');e.holdConfirm(1200);e.tick(10000);
  assert.equal(e.powerState().stage,'active');e.config.reducedMotion=true;assert.equal(e.powerState().fps,0);
});
test('profiles round trip, preserve per-key colors, and reject corruption',()=>{
  const e=new Engine();e.paint(['1','55'],'#edc08c');const original=serialize(e.config);
  assert.deepEqual(deserialize(original),e.config);assert.equal(deserialize(original).lighting.perKey['55'],'#edc08c');
  assert.throws(()=>deserialize(original.replace('edc08c','000000')),/checksum/);
  e.save();e.toggleCaps(false);e.reboot();assert.equal(e.config.capsSwap,true);
});
test('wheel/menu bounds and invalid battery-independent profile values',()=>{
  const e=new Engine();e.turn(-100);assert.equal(e.volume,0);e.press();e.turn(-1);e.turn(-1);assert.equal(e.cursor,4);e.press();assert.equal(e.page,'Focus');
  const c=defaults();c.lighting.brightness=101;assert.throws(()=>serialize(c),/Invalid lighting/);
});
test('close detents group menu input, reset on reversal and expire partial steps',()=>{
  const e=new Engine();e.press();e.turn(1);assert.equal(e.cursor,0);e.turn(1);assert.equal(e.cursor,1);
  e.turn(1);e.turn(-1);assert.equal(e.cursor,1);e.turn(-1);assert.equal(e.cursor,0);
  e.turn(1);e.tick(300);e.turn(1);assert.equal(e.cursor,0);
  e.controlKey('ArrowDown');assert.equal(e.cursor,1);
});
test('screen appearance persists and old profiles acquire the dark default',()=>{
  const e=new Engine();e.page='Keys';e.cursor=3;e.press();assert.equal(e.config.screenTheme,'Light');
  e.save();e.config.screenTheme='Dark';e.reboot();assert.equal(e.config.screenTheme,'Light');
  const old=defaults();delete old.screenTheme;assert.equal(new Engine(old).config.screenTheme,'Dark');
  old.screenTheme='invalid';assert.throws(()=>new Engine(old),/appearance/);
});
test('wheel edits values without leaving the row or wrapping at the bounds',()=>{
  const e=new Engine();e.page='Lighting';e.cursor=1;e.config.lighting.brightness=98;e.press();assert.equal(e.editing,true);
  for(let i=0;i<8;i++){e.tick(20);e.turn(1);}assert.equal(e.config.lighting.brightness,100);assert.equal(e.cursor,1);
  e.tick(200);e.turn(-1);assert.equal(e.config.lighting.brightness,99);e.press();assert.equal(e.editing,false);
});
