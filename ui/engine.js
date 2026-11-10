(function (root) {
  'use strict';
  const HOSTS = ['usb', 'bt1', 'bt2', 'bt3', 'rf'];
  const SECTIONS = ['Devices', 'Keys', 'Lighting', 'Power', 'Focus'];
  const EFFECTS = ['Still', 'Tidal', 'Rain', 'Trails', 'Constellation'];
  const POLICIES = {
    Balanced: { dim: 15000, off: 45000, sleep: 180000, rgbCap: 40, screen: 65, fps: 12 },
    Endurance: { dim: 8000, off: 25000, sleep: 90000, rgbCap: 18, screen: 40, fps: 8 },
    Desk: { dim: 60000, off: 180000, sleep: 600000, rgbCap: 75, screen: 85, fps: 20 }
  };
  function defaults() {
    return { version: 1, capsSwap: true, activeHost: 'usb',
      hosts: {
        usb: { name: 'USB cable', os: 'mac', bonded: true },
        bt1: { name: 'Laptop', os: 'mac', bonded: true },
        bt2: { name: 'Device 2', os: 'windows', bonded: false },
        bt3: { name: 'Device 3', os: 'mac', bonded: false },
        rf: { name: 'Receiver', os: 'windows', bonded: true }
      },
      lighting: { effect: 'Tidal', color: '#91e2ce', brightness: 28, speed: 35, perKey: {} },
      power: 'Balanced', reducedMotion: false, wheel: 'Volume', screenFace: 'Chibi', screenTheme: 'Dark',
      layerColors: { Base: '#91e2ce', Function: '#f2c38b', Control: '#c5b4f4' }
    };
  }
  function validateConfig(value) {
    if (!value || value.version !== 1 || typeof value.capsSwap !== 'boolean' || !HOSTS.includes(value.activeHost)) throw Error('Unsupported configuration');
    if (!POLICIES[value.power] || !EFFECTS.includes(value.lighting?.effect)) throw Error('Invalid lighting or power profile');
    for (const n of ['brightness', 'speed']) if (!Number.isInteger(value.lighting[n]) || value.lighting[n] < 0 || value.lighting[n] > 100) throw Error('Invalid lighting value');
    if (!/^#[0-9a-f]{6}$/i.test(value.lighting.color)) throw Error('Invalid color');
    if (!['Volume', 'Scroll', 'Brightness'].includes(value.wheel) || !['Orbit', 'Minimal', 'Constellation','Chibi'].includes(value.screenFace)) throw Error('Invalid display or wheel setting');
    if (typeof value.reducedMotion !== 'boolean' || !value.layerColors || !value.lighting.perKey || Object.keys(value.lighting.perKey).length > 144) throw Error('Invalid profile data');
    for (const color of [...Object.values(value.layerColors), ...Object.values(value.lighting.perKey)]) if (!/^#[0-9a-f]{6}$/i.test(color)) throw Error('Invalid key color');
    for (const id of HOSTS) {
      const h = value.hosts?.[id];
      if (!h || typeof h.name !== 'string' || !h.name.trim() || h.name.length > 18 || !['mac', 'windows', 'android'].includes(h.os) || typeof h.bonded !== 'boolean') throw Error('Invalid device profile');
    }
    if(value.screenTheme!==undefined&&!['Dark','Light'].includes(value.screenTheme))throw Error('Invalid screen appearance');
    return {...structuredClone(value),screenTheme:value.screenTheme??'Dark'};
  }
  function crc32(str) {
    let crc = -1;
    for (const byte of new TextEncoder().encode(str)) {
      crc ^= byte;
      for (let i = 0; i < 8; i++) crc = (crc >>> 1) ^ (0xedb88320 & -(crc & 1));
    }
    return ((crc ^ -1) >>> 0).toString(16).padStart(8, '0');
  }
  function serialize(config) {
    const payload = JSON.stringify(validateConfig(config));
    return JSON.stringify({ format: 'f75-studio', payload, checksum: crc32(payload) });
  }
  function deserialize(text) {
    const record = JSON.parse(text);
    if (record.format !== 'f75-studio' || typeof record.payload !== 'string' || record.checksum !== crc32(record.payload)) throw Error('Configuration checksum failed');
    return validateConfig(JSON.parse(record.payload));
  }
  class Engine {
    constructor(config = defaults()) {
      this.config = validateConfig(config); this.saved = serialize(this.config);
      this.page = 'Home'; this.cursor = 0; this.editing = false; this.lastEditTurn = null; this.control = false; this.functionLayer = false;
      this.wheelDivisor=2;this.wheelPending=0;this.lastMenuTurn=null;this.editStreak=0;this.lastEditDirection=0;
      this.pairing = null; this.confirm = null; this.connected = this.config.activeHost === 'usb' ? 'usb' : null;
      this.lastActivity = 0; this.time = 0; this.battery = 78; this.charging = false;
      this.volume = 42; this.action = ''; this.error = ''; this.dirty = false;
      this.effects = []; this.keysDown = new Map(); this.notice = ''; this.noticeUntil = 0;
    }
    host() { return this.config.hosts[this.config.activeHost]; }
    layer() { return this.control ? 'Control' : this.functionLayer ? 'Function' : 'Base'; }
    changed() { this.dirty = serialize(this.config) !== this.saved; }
    toast(message) { this.notice = message; this.noticeUntil = this.time + 2400; }
    activity() {
      const asleep = this.powerState().stage === 'sleep'; this.lastActivity = this.time;
      if (asleep) this.toast('Awake');
    }
    releaseKeys() {
      for (const [physical, usage] of this.keysDown) this.effects.push({ type: 'keyUp', physical, usage });
      this.keysDown.clear();
    }
    mapUsage(usage) {
      if (this.config.capsSwap) { if (usage === 0x39) usage = 0xe0; else if (usage === 0xe0) usage = 0x39; }
      if (this.host().os === 'mac') {
        return ({ 224: 227, 228: 231, 226: 227, 227: 226, 230: 231, 231: 230 })[usage] ?? usage;
      }
      return usage;
    }
    keyDown(physical, usage) {
      this.activity();
      if (this.control) return this.controlKey(physical);
      if (this.keysDown.has(physical)) return;
      const mapped = this.mapUsage(usage); this.keysDown.set(physical, mapped);
      this.effects.push({ type: 'keyDown', physical, usage: mapped });
      return mapped;
    }
    keyUp(physical) {
      if (!this.keysDown.has(physical)) return;
      this.effects.push({ type: 'keyUp', physical, usage: this.keysDown.get(physical) });
      this.keysDown.delete(physical);
    }
    setControl(on) {
      this.releaseKeys(); this.control = on; this.activity();
      this.toast(on ? 'Board controls' : 'Typing resumed');
    }
    controlKey(key) {
      this.activity();
      if (['1', '2', '3', '4','5'].includes(key)) { this.page = SECTIONS[Number(key) - 1]; this.cursor = 0;this.editing=false;this.wheelPending=0; }
      else if (['ArrowDown','j','ArrowRight','ArrowUp','k','ArrowLeft'].includes(key)) {
        const divisor=this.wheelDivisor;this.wheelDivisor=1;this.wheelPending=0;
        this.turn(['ArrowDown','j','ArrowRight'].includes(key)?1:-1);this.wheelDivisor=divisor;
      }
      else if (key === 'Enter') this.press();
      else if (key === 'Escape') this.back();
      else if (key === 's') this.save();
      else if (key === 'm') this.setOS(this.host().os === 'mac' ? 'windows' : 'mac');
    }
    setOS(os) {
      if (!['auto', 'mac', 'windows', 'android'].includes(os)) return;
      this.releaseKeys(); this.host().automatic = os === 'auto'; if(os !== 'auto') this.host().os = os; this.changed(); this.activity();
      this.toast(os === 'auto' ? 'Automatic layout' : os === 'mac' ? 'Mac layout' : os === 'android' ? 'Android layout' : 'Windows layout');
    }
    toggleCaps(value = !this.config.capsSwap) {
      this.releaseKeys(); this.config.capsSwap = Boolean(value); this.changed(); this.activity();
      this.toast(this.config.capsSwap ? 'Caps / Ctrl swapped' : 'Original Caps / Ctrl');
    }
    switchHost(id) {
      if (!HOSTS.includes(id) || this.pairing) return false;
      this.releaseKeys(); this.config.activeHost = id; this.connected = null;
      this.effects.push({ type: 'connect', slot: id }); this.changed(); this.activity();
      this.toast('Connecting ' + id.toUpperCase()); return true;
    }
    connectedEvent(id) {
      if (this.pairing && this.pairing.id !== id) return false;
      if (!this.pairing && this.config.activeHost !== id) return false;
      this.connected = id;
      if (this.pairing) {
        this.config.hosts[id].bonded = true; this.config.activeHost = id; this.pairing = null;
        this.effects.push({ type: 'persistBond', slot: id }); this.changed();
      }
      this.error = ''; this.toast('Connected'); return true;
    }
    requestPair(id) {
      if (!['bt1', 'bt2', 'bt3'].includes(id) || this.pairing) return false;
      this.confirm = { type: 'pair', id, replacing: this.config.hosts[id].bonded };
      this.page = 'Devices'; this.cursor = HOSTS.indexOf(id); this.activity(); return true;
    }
    holdConfirm(milliseconds) {
      if (!this.confirm || milliseconds < 1200) return false;
      const id = this.confirm.id; this.confirm = null; this.releaseKeys();
      this.pairing = { id, deadline: this.time + 30000 }; this.error = '';
      this.effects.push({ type: 'pair', slot: id }); this.activity(); return true;
    }
    cancelPairing() {
      if (this.pairing) this.effects.push({ type: 'cancelPair', slot: this.pairing.id });
      this.pairing = null; this.confirm = null; this.error = ''; this.toast('Pairing canceled');
    }
    rows() {
      if (this.page === 'Menu') return SECTIONS;
      if (this.page === 'Devices') return HOSTS;
      if (this.page === 'Keys') return ['Operating system', 'Caps / Ctrl', 'Wheel action','Screen appearance', 'Save settings'];
      if (this.page === 'Lighting') return ['Effect', 'Brightness', 'Speed', 'Color', 'Save settings'];
      if (this.page === 'Power') return ['Balanced', 'Endurance', 'Desk', 'Save settings'];
      if (this.page === 'Focus') return ['Start / pause','Next session','Reset cycle'];
      return [];
    }
    turn(direction) {
      this.activity(); if (this.confirm || this.pairing) return;
      if(this.editing){
        const elapsed=this.lastEditTurn===null?Infinity:this.time-this.lastEditTurn;
        this.editStreak=elapsed<90&&this.lastEditDirection===Math.sign(direction)?Math.min(3,this.editStreak+1):0;this.lastEditDirection=Math.sign(direction);
        const step=this.editStreak>=3?3:1;this.lastEditTurn=this.time;
        this.setLighting(this.cursor===1?'brightness':'speed',this.config.lighting[this.cursor===1?'brightness':'speed']+Math.sign(direction)*step);return;
      }
      if (this.page === 'Home') {
        if (this.config.wheel === 'Volume') this.volume = Math.min(100, Math.max(0, this.volume + direction * 2));
        if (this.config.wheel === 'Brightness') this.setLighting('brightness', this.config.lighting.brightness + direction * 2);
        this.action = this.config.wheel; this.effects.push({ type: this.config.wheel.toLowerCase(), delta: direction });
      } else {
        if(this.lastMenuTurn===null||this.time-this.lastMenuTurn>250||this.wheelPending*direction<0)this.wheelPending=0;
        this.lastMenuTurn=this.time;this.wheelPending+=Math.sign(direction);
        if(Math.abs(this.wheelPending)<this.wheelDivisor)return;
        this.wheelPending=0;const n = this.rows().length;this.cursor = (this.cursor + Math.sign(direction) + n) % n;
      }
    }
    press() {
      this.activity(); if (this.confirm || this.pairing) return;
      if(this.editing){this.editing=false;this.lastEditTurn=null;return;}
      this.wheelPending=0;
      if (this.page === 'Home') { this.page = 'Menu'; this.cursor = 0; return; }
      if (this.page === 'Menu') { this.page = SECTIONS[this.cursor]; this.cursor = 0; return; }
      if (this.page === 'Devices') { const id = HOSTS[this.cursor]; this.switchHost(id); return; }
      if (this.page === 'Keys') {
        if (this.cursor === 0) this.setOS(this.host().automatic ? 'mac' : this.host().os === 'mac' ? 'windows' : this.host().os === 'windows' ? 'android' : 'auto');
        if (this.cursor === 1) this.toggleCaps();
        if (this.cursor === 2) { const modes = ['Volume', 'Scroll', 'Brightness']; this.config.wheel = modes[(modes.indexOf(this.config.wheel) + 1) % modes.length]; this.changed(); }
        if (this.cursor === 3){this.config.screenTheme=this.config.screenTheme==='Dark'?'Light':'Dark';this.changed();}
        if (this.cursor === 4) this.save();
      }
      if (this.page === 'Lighting') {
        if (this.cursor === 0) this.setLighting('effect', EFFECTS[(EFFECTS.indexOf(this.config.lighting.effect) + 1) % EFFECTS.length]);
        if (this.cursor === 1 || this.cursor === 2) {this.editing=true;this.lastEditTurn=null;}
        if (this.cursor === 3) {const colors=['#91e2ce','#f2a4aa','#c4b4ef','#a4c8f2','#edc08c','#ffffff'];this.setLighting('color',colors[(colors.indexOf(this.config.lighting.color)+1)%colors.length]);}
        if (this.cursor === 4) this.save();
      }
      if (this.page === 'Power') {
        if (this.cursor < 3) { this.config.power = this.rows()[this.cursor]; this.changed(); }
        else this.save();
      }
    }
    back() {
      this.activity();
      this.wheelPending=0;
      if (this.pairing || this.confirm) { this.cancelPairing(); return; }
      if(this.editing){this.editing=false;this.lastEditTurn=null;return;}
      this.page = this.page === 'Menu' ? 'Home' : 'Menu'; this.cursor = 0;
    }
    setLighting(key, value) {
      if (['brightness', 'speed'].includes(key)) value = Math.max(0, Math.min(100, Math.round(value)));
      if (key === 'effect' && !EFFECTS.includes(value)) return;
      if (key === 'color' && !/^#[0-9a-f]{6}$/i.test(value)) return;
      this.config.lighting[key] = value; this.changed(); this.activity();
    }
    paint(keys, color) {
      if (!/^#[0-9a-f]{6}$/i.test(color)) return;
      for (const key of keys) this.config.lighting.perKey[key] = color;
      this.changed(); this.activity();
    }
    tick(milliseconds) {
      this.time += milliseconds;
      if (this.pairing && this.time >= this.pairing.deadline) {
        this.effects.push({ type: 'cancelPair', slot: this.pairing.id }); this.pairing = null;
        this.error = 'No host found. Try pairing again.';
      }
      if (this.time >= this.noticeUntil) this.notice = '';
    }
    powerState() {
      const p = POLICIES[this.config.power]; const idle = this.time - this.lastActivity;
      const stage = this.pairing || this.confirm ? 'active' : idle >= p.sleep ? 'sleep' : idle >= p.off ? 'off' : idle >= p.dim ? 'dim' : 'active';
      const low = !this.charging && this.battery <= 10;
      const critical = !this.charging && this.battery <= 5;
      let rgb = Math.min(this.config.lighting.brightness, this.charging ? 100 : p.rgbCap);
      let screen = p.screen;
      if (low) { rgb = Math.min(rgb, 8); screen = Math.min(screen, 25); }
      if (critical) { rgb = 0; screen = 10; }
      if (stage === 'dim') { rgb = Math.min(rgb, 4); screen = Math.min(screen, 16); }
      if (stage === 'off' || stage === 'sleep') rgb = screen = 0;
      return { stage, rgb, screen, fps: this.config.reducedMotion || stage !== 'active' || low ? 0 : p.fps, low, critical };
    }
    save() { this.saved = serialize(this.config); this.dirty = false; this.effects.push({ type: 'save', record: this.saved }); this.toast('Settings saved'); return this.saved; }
    reboot() { const record = this.saved; Object.assign(this, new Engine(deserialize(record))); this.toast('Saved settings restored'); }
  }
  const api = { Engine, defaults, validateConfig, serialize, deserialize, crc32, HOSTS, SECTIONS, EFFECTS, POLICIES };
  if (typeof module !== 'undefined') module.exports = api;
  else root.F75 = api;
})(typeof window !== 'undefined' ? window : globalThis);
