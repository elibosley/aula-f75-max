#!/usr/bin/env python3
"""Tailnet preview backed by the compiled firmware control core and pixel renderer."""
import argparse
import base64
import ctypes as C
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
import re
import struct
import threading
import time
import zlib
from display_types import View

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / '.runtime'
RUNTIME.mkdir(mode=0o700, exist_ok=True)
LIB = C.CDLL(str(ROOT / 'analysis/libf75.dylib'))

class Config(C.Structure):
    _fields_ = [('os',C.c_uint8*5),('names',(C.c_char*19)*5)] + [(n,C.c_uint8) for n in ['active_host','bonded_mask','caps_swap','power','brightness','speed','effect','wheel','face','reduced_motion']] + [('color',C.c_uint8*3),('light_mode',C.c_uint8),('os_auto_mask',C.c_uint8)]
class State(C.Structure):
    _fields_ = [('config',Config)] + [(n,C.c_uint32) for n in ['last_activity','pair_started','transaction','release_epoch']] + [('pair_slot',C.c_uint8),('connected_slot',C.c_uint8),('pairing',C.c_int),('control_layer',C.c_bool)]
class Budget(C.Structure):
    _fields_ = [('stage',C.c_int),('rgb',C.c_uint8),('screen',C.c_uint8),('animation_fps',C.c_uint8)]
class Timer(C.Structure):
    _fields_=[(n,C.c_uint32) for n in ['remaining_ms','last_tick','finished_at']]+[('phase',C.c_uint8),('completed',C.c_uint8),('running',C.c_bool),('alert',C.c_bool)]
class Pet(C.Structure):
    _fields_=[(n,C.c_uint32) for n in ['bucket_at','last_key','last_effect','effect_started','rng','next_blink','blink_started']]+[('buckets',C.c_uint16*16),('wpm',C.c_uint16)]+[(n,C.c_uint8) for n in ['bucket','mode','effect','previous_effect']]+[('has_key',C.c_bool),('blinking',C.c_bool)]
class PetFrame(C.Structure):
    _fields_=[('wpm',C.c_uint16)]+[(n,C.c_uint8) for n in ['mode','frame','effect','phase']]+[('bob',C.c_int8)]
class Navigation(C.Structure):
    _fields_=[(n,C.c_uint8) for n in ['page','cursor','volume','editing','wheel_divisor','edit_streak']]+[('wheel_pending',C.c_int8),('last_direction',C.c_int8),('last_turn',C.c_uint32)]
class Motion(C.Structure):
    _fields_=[(n,C.c_int32) for n in ['selection','velocity','slide','slide_velocity']]+[(n,C.c_uint32) for n in ['last_step','last_input']]+[('context',C.c_uint16),('selected',C.c_uint8),('flags',C.c_uint8)]
HOSTS=['usb','bt1','bt2','bt3','rf'];POWERS=['Balanced','Endurance','Desk'];EFFECTS=['Still','Tidal','Rain','Trails','Constellation'];WHEELS=['Volume','Scroll','Brightness'];FACES=['Orbit','Minimal','Constellation','Chibi']
PAGES=['Home','Menu','Devices','Keys','Lighting','Power','Focus']
PState=C.POINTER(State);PConfig=C.POINTER(Config);U32=C.c_uint32;U8=C.c_uint8
def bind(name,args,restype=None):
    f=getattr(LIB,name);f.argtypes=args;f.restype=restype;return f
init=bind('f75_init',[PState,PConfig,U32]);set_os=bind('f75_set_os',[PState,C.c_int],C.c_bool)
set_caps=bind('f75_set_caps_swap',[PState,C.c_bool]);control=bind('f75_set_control_layer',[PState,C.c_bool]);activity=bind('f75_activity',[PState,U32])
switch=bind('f75_switch_host',[PState,U8,U32],U32);request=bind('f75_pair_request',[PState,U8,U32],C.c_bool)
confirm=bind('f75_pair_confirm',[PState,U32,U32],U32);ack=bind('f75_host_ack',[PState,U8,U32],C.c_bool)
cancel=bind('f75_pair_cancel',[PState]);tick=bind('f75_tick',[PState,U32])
budget=bind('f75_power_budget',[PState,U32,U8,C.c_bool],Budget);map_usage=bind('f75_map_usage',[PState,C.c_uint16],C.c_uint16)
encode=bind('f75_record_encode',[PConfig,U32,C.POINTER(U8)])
select=bind('f75_record_select',[C.POINTER(U8),C.POINTER(U8),PConfig,C.POINTER(U32)],C.c_bool)
lighting_frame=bind('f75_lighting_frame',[PConfig,U8,U32,C.POINTER(U8)])
render_tile=bind('f75_render_tile',[C.POINTER(View),U8,U8,C.POINTER(C.c_uint16),C.c_size_t],C.c_bool)
motion_update=bind('f75_motion_update',[C.POINTER(Motion),C.c_uint16,U8,C.c_int,U32,C.c_bool])
motion_apply=bind('f75_motion_apply',[C.POINTER(Motion),C.POINTER(View)])
motion_active=bind('f75_motion_active',[C.POINTER(Motion)],C.c_bool)
motion_nudge=bind('f75_motion_nudge',[C.POINTER(Motion),C.c_int,U32])
nav_init=bind('f75_navigation_init',[C.POINTER(Navigation)])
open_page=bind('f75_open_page',[C.POINTER(Navigation),C.c_int])
turn=bind('f75_turn',[PState,C.POINTER(Navigation),C.c_int,U32],C.c_int)
press=bind('f75_press',[PState,C.POINTER(Navigation),U32],C.c_int)
back=bind('f75_back',[PState,C.POINTER(Navigation),U32])
control_key=bind('f75_control_key',[PState,C.POINTER(Navigation),C.c_uint16,U32],C.c_int)
timer_init=bind('f75_timer_init',[C.POINTER(Timer),U32])
timer_tick=bind('f75_timer_tick',[C.POINTER(Timer),U32])
timer_toggle=bind('f75_timer_toggle',[C.POINTER(Timer),U32])
timer_next=bind('f75_timer_next',[C.POINTER(Timer),U32])
timer_pulse=bind('f75_timer_pulse',[C.POINTER(Timer),U32,C.c_bool],C.c_bool)
timer_budget=bind('f75_timer_budget',[C.POINTER(Timer),Budget],Budget)
pet_init=bind('f75_pet_init',[C.POINTER(Pet),U32,U32])
pet_tick=bind('f75_pet_tick',[C.POINTER(Pet),U32])
pet_tap=bind('f75_pet_tap',[C.POINTER(Pet),U32])
pet_get_frame=bind('f75_pet_get_frame',[C.POINTER(Pet),U32,C.c_bool],PetFrame)
assert C.sizeof(Config)==115 and C.sizeof(State)==144 and C.sizeof(Timer)==16

def png(rgb):
    def chunk(kind,data):return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
    scan=b''.join(b'\0'+rgb[y*384:(y+1)*384] for y in range(128))
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',128,128,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(scan))+chunk(b'IEND',b'')

class Session:
    def __init__(self,sid):
        self.sid=sid;self.state=State();init(C.byref(self.state),None,0);self.navigation=Navigation();nav_init(C.byref(self.navigation))
        self.started=time.monotonic();self.offset=0;self.seq=0;self.generation=0;self.battery=78;self.usb=False;self.system_motion=False;self.aux={};self.error='';self.lock=threading.RLock();self.saved=Config();self.saved_aux={};self.last_view=None
        self.motion=Motion();self.direction=1;self.display_fps=0;self.timer=Timer();timer_init(C.byref(self.timer),0);self.pet=Pet();pet_init(C.byref(self.pet),0,secrets.randbits(32))
        self.load()
    def now(self):return int((time.monotonic()-self.started)*1000+self.offset)&0xffffffff
    def tick_all(self):
        now=self.now();was_alert=self.timer.alert
        timer_tick(C.byref(self.timer),now);tick(C.byref(self.state),now)
        pet_tick(C.byref(self.pet),now)
        if self.timer.alert and not was_alert:activity(C.byref(self.state),now)
    def paths(self):return [RUNTIME/(self.sid+'-'+letter+'.bin') for letter in ['a','b']]
    def load(self):
        records=[]
        for path in self.paths():
            data=path.read_bytes() if path.exists() else bytes(160)
            records.append((U8*160).from_buffer_copy(data[:160].ljust(160,b'\0')))
        gen=U32();config=Config()
        if select(records[0],records[1],C.byref(config),C.byref(gen)):
            self.generation=gen.value;init(C.byref(self.state),C.byref(config),self.now())
        self.saved=Config.from_buffer_copy(self.state.config)
        aux=RUNTIME/(self.sid+'-aux.json')
        if aux.exists():
            try:self.aux=json.loads(aux.read_text())
            except (ValueError,OSError):pass
        self.saved_aux=json.loads(json.dumps(self.aux))
    def save(self):
        self.generation+=1;out=(U8*160)();encode(C.byref(self.state.config),self.generation,out)
        path=self.paths()[self.generation%2];temporary=path.with_suffix('.tmp')
        with temporary.open('wb') as f:f.write(bytes(out));f.flush();import os;os.fsync(f.fileno())
        temporary.replace(path);self.saved=Config.from_buffer_copy(self.state.config)
        self.saved_aux=json.loads(json.dumps(self.aux));aux=RUNTIME/(self.sid+'-aux.json');tmp=aux.with_suffix('.tmp');tmp.write_text(json.dumps(self.aux));tmp.replace(aux)
    def update_visual_settings(self,config):
        if not config:return
        c=self.state.config;l=config.get('lighting',{})
        for key,target in [('brightness','brightness'),('speed','speed')]:
            value=l.get(key,getattr(c,target))
            if isinstance(value,int) and not isinstance(value,bool) and 0<=value<=100:setattr(c,target,value)
        for key,choices,target in [('power',POWERS,'power'),('wheel',WHEELS,'wheel'),('screenFace',FACES,'face'),('screenTheme',['Dark','Light'],'light_mode')]:
            if config.get(key) in choices:setattr(c,target,choices.index(config[key]))
        if l.get('effect') in EFFECTS:c.effect=EFFECTS.index(l['effect'])
        color=l.get('color','')
        if isinstance(color,str) and len(color)==7:
            try:c.color[:]=bytes.fromhex(color[1:])
            except ValueError:pass
        c.reduced_motion=bool(config.get('reducedMotion',c.reduced_motion))
        for i,id in enumerate(HOSTS):
            name=config.get('hosts',{}).get(id,{}).get('name')
            if isinstance(name,str) and name.strip():c.names[i].value=name.strip().encode('ascii','replace')[:18]
        # Per-key paint and layer palettes are simulator metadata pending an RGB adapter.
        self.aux={'perKey':l.get('perKey',{}),'layerColors':config.get('layerColors',{}),'screenColor':config.get('screenColor',self.aux.get('screenColor'))}
    def command(self,name,args):
        self.tick_all()
        s=C.byref(self.state);now=self.now()
        ui_action=0
        if name=='activity':activity(s,now)
        elif name=='visualSettings':self.update_visual_settings(args[0]);activity(s,now)
        elif name=='setOS' and args[0]=='auto':self.state.config.os_auto_mask|=1<<self.state.config.active_host
        elif name=='setOS' and args[0] in ['mac','windows','android']:set_os(s,['mac','windows','android'].index(args[0]))
        elif name=='toggleCaps':set_caps(s,bool(args[0]))
        elif name=='setControl':control(s,bool(args[0]))
        elif name=='switchHost' and args[0] in HOSTS:switch(s,HOSTS.index(args[0]),now)
        elif name=='requestPair' and args[0] in HOSTS:
            if request(s,HOSTS.index(args[0]),now):self.error=''
        elif name=='holdConfirm':confirm(s,min(max(int(args[0]),0),100000),now)
        elif name=='connectedEvent' and args[0] in HOSTS:
            # The browser button represents a simulated transport acknowledgement.
            if not self.state.transaction:switch(s,self.state.config.active_host,now)
            ack(s,HOSTS.index(args[0]),self.state.transaction)
        elif name=='cancelPairing':cancel(s);self.error=''
        elif name=='tick' and args and int(args[0])>=5000:self.offset+=min(int(args[0]),600000)
        elif name=='timerToggle':timer_toggle(C.byref(self.timer),now);activity(s,now)
        elif name=='timerNext':timer_next(C.byref(self.timer),now);activity(s,now)
        elif name=='timerReset':timer_init(C.byref(self.timer),now);activity(s,now)
        elif name=='petTaps':
            if not args or isinstance(args[0],bool) or not isinstance(args[0],int) or not 1<=args[0]<=64:raise ValueError('Pet input must be a count from 1 to 64')
            if not self.state.control_layer:
                for _ in range(args[0]):pet_tap(C.byref(self.pet),now)
            activity(s,now)
        elif name=='timerDemo':
            if not self.timer.running:timer_toggle(C.byref(self.timer),now)
            self.offset+=self.timer.remaining_ms
        elif name=='save':self.save()
        elif name=='openPage' and args[0] in PAGES:
            open_page(C.byref(self.navigation),PAGES.index(args[0]));activity(s,now)
        elif name=='turn':
            self.direction=-1 if int(args[0])<0 else 1
            ui_action=turn(s,C.byref(self.navigation),int(args[0]),now)
            if self.navigation.wheel_pending:motion_nudge(C.byref(self.motion),self.direction,now)
        elif name=='wheelFeel' and int(args[0]) in [1,2,3]:
            self.navigation.wheel_divisor=int(args[0]);self.navigation.wheel_pending=0
        elif name=='press':
            if self.timer.alert and self.state.pairing==0 and not self.state.control_layer:
                timer_next(C.byref(self.timer),now);open_page(C.byref(self.navigation),6);activity(s,now)
            else:ui_action=press(s,C.byref(self.navigation),now)
        elif name=='back':self.direction=-1;back(s,C.byref(self.navigation),now)
        elif name=='controlKey':
            usages={'1':0x1e,'2':0x1f,'3':0x20,'4':0x21,'5':0x22,'ArrowUp':0x52,'ArrowDown':0x51,'ArrowLeft':0x50,'ArrowRight':0x4f,'j':0x0d,'k':0x0e,'Enter':0x28,'Escape':0x29,'s':0x16,'m':0x10}
            if args[0] in usages:ui_action=control_key(s,C.byref(self.navigation),usages[args[0]],now)
        elif name=='importProfile':
            config=args[0]
            self.update_visual_settings(config)
            for i,id in enumerate(HOSTS):
                os=config.get('hosts',{}).get(id,{}).get('os')
                if os in ['mac','windows','android']:self.state.config.os[i]=['mac','windows','android'].index(os)
                if config.get('hosts',{}).get(id,{}).get('automatic',True):self.state.config.os_auto_mask|=1<<i
                else:self.state.config.os_auto_mask&=~(1<<i)
            set_caps(s,bool(config.get('capsSwap',True)))
            target=config.get('activeHost','usb')
            if target in HOSTS:self.state.config.active_host=HOSTS.index(target)
            self.state.release_epoch+=1;self.save()
        elif name=='reboot':
            init(s,C.byref(self.saved),now);nav_init(C.byref(self.navigation));timer_init(C.byref(self.timer),now);self.motion=Motion();self.aux=json.loads(json.dumps(self.saved_aux));self.error=''
            pet_init(C.byref(self.pet),now,secrets.randbits(32))
        if ui_action==1:self.save()
        if ui_action==4:timer_toggle(C.byref(self.timer),now)
        if ui_action==5:timer_next(C.byref(self.timer),now)
        if ui_action==6:timer_init(C.byref(self.timer),now)
        self.tick_all()
        if self.state.pairing==3:self.error='No host found. Try pairing again.'
        elif name in ['back','press','cancelPairing','requestPair']:self.error=''
    def config_json(self):
        c=self.state.config
        return {'version':1,'capsSwap':bool(c.caps_swap),'activeHost':HOSTS[c.active_host],
            'hosts':{id:{'name':bytes(c.names[i]).split(b'\0')[0].decode('ascii'),'os':['mac','windows','android'][c.os[i]],'automatic':bool(c.os_auto_mask&(1<<i)),'bonded':bool(c.bonded_mask&(1<<i)) or i==0} for i,id in enumerate(HOSTS)},
            'lighting':{'effect':EFFECTS[c.effect],'brightness':c.brightness,'speed':c.speed,'color':'#'+bytes(c.color).hex(),'perKey':self.aux.get('perKey',{})},
            'power':POWERS[c.power],'reducedMotion':bool(c.reduced_motion),'wheel':WHEELS[c.wheel],'screenFace':FACES[c.face],'screenTheme':['Dark','Light'][c.light_mode],
            'screenColor':self.aux.get('screenColor'),'layerColors':self.aux.get('layerColors') or {'Base':'#91e2ce','Function':'#edc08c','Control':'#c4b4ef'}}
    def frame(self,view):
        page=PAGES[self.navigation.page]
        c=self.state.config
        rows={'Menu':['Devices','Keys','Lighting','Power','Focus'],'Devices':[HOSTS[i].upper()+' '+bytes(c.names[i]).split(b'\0')[0].decode() for i in range(5)],'Keys':[('Auto: ' if c.os_auto_mask&(1<<c.active_host) else 'Layout: ')+['Mac','Windows','Android'][c.os[c.active_host]],'Caps: '+(('Command' if c.os[c.active_host]==0 else 'Ctrl') if c.caps_swap else 'Normal'),'Wheel: '+WHEELS[c.wheel],'Screen: '+('Light' if c.light_mode else 'Dark'),'Save settings'],'Lighting':['Effect: '+EFFECTS[c.effect],f'Brightness {c.brightness}%',f'Speed {c.speed}%','Color: '+('Custom' if bytes(c.color).hex() not in ['91e2ce','f2a4aa','c4b4ef','a4c8f2','edc08c','ffffff'] else ['Mint','Rose','Lilac','Ocean','Peach','White'][['91e2ce','f2a4aa','c4b4ef','a4c8f2','edc08c','ffffff'].index(bytes(c.color).hex())]),'Save settings'],'Power':['Balanced','Endurance','Desk','Save settings']}.get(page,[])
        start=0
        view={**view,'home':page=='Home','title':page,'rows':rows[:5],'selected':self.navigation.cursor-start}
        if page=='Home' and view.get('footer') in ('PRESS FOR MENU','Press for menu','Press wheel: Menu'):view['footer']=''
        if self.navigation.editing:view['footer']='TURN / PRESS done'
        if self.state.control_layer:view.update(home=False,title='Board controls',rows=['1 Devices  2 Keys','3 Lights   4 Power','5 Focus   J K move','Enter selects'],selected=255,footer='Esc back   S save')
        if self.state.pairing==1:view.update(home=False,title='Replace device?' if self.state.config.bonded_mask&(1<<self.state.pair_slot) else 'Pair device?',rows=[HOSTS[self.state.pair_slot].upper(),'Hold Enter 1.2 sec','Esc cancels'],selected=255,footer='Hold to confirm')
        if self.state.pairing==2:view.update(home=False,title='Pairing',rows=[HOSTS[self.state.pair_slot].upper(),'Open Bluetooth','On your computer'],selected=255,footer=str(max(0,30-(self.now()-self.state.pair_started)//1000))+' sec remaining')
        if self.state.pairing==3:view.update(home=False,title='Pairing timed out',rows=['No host found','Press to retry','Back to cancel'],selected=255,footer='Device not replaced')
        friendly_footers={'TURN / PRESS / BACK':'Turn / press / back','PRESS FOR MENU':'','TURN / PRESS DONE':'Turn / press done'}
        view['footer']=friendly_footers.get(view.get('footer'),view.get('footer',''))
        v=View()
        for name,limit in [('status_left',7),('status_right',7),('title',19),('footer',20),('clock',5),('host_label',18),('os',3)]:
            setattr(v,name,str(view.get(name,'')).encode('ascii','replace')[:limit])
        for i,row in enumerate(view.get('rows',[])[:5]):v.rows[i].value=str(row).encode('ascii','replace')[:19]
        v.selected=int(view.get('selected',255))%256;v.home=bool(view.get('home'));v.caps_swap=bool(self.state.config.caps_swap)
        b=self.power_budget()
        v.face=self.state.config.face
        v.animation_phase=(self.now()//100)%16 if b.animation_fps else 0
        if b.stage>=2:
            v.home=False;v.title=b'Display off' if b.stage==2 else b'Sleep';v.rows[0].value=b'Any key to wake';v.footer=b'Power saving';v.selected=255
        v.light_mode=bool(c.light_mode)
        timer_visible=(page=='Focus' or (page=='Home' and self.timer.running and c.face!=3) or self.timer.alert) and not self.state.control_layer and self.state.pairing==0 and b.stage<2
        if timer_visible:
            t=self.timer;seconds=(t.remaining_ms+999)//1000;duration=[1500000,300000,900000][t.phase]
            v.timer=True;v.home=False;v.clock=f'{seconds//60:02}:{seconds%60:02}'.encode()
            v.title=('Session complete' if t.alert else ['Focus','Short break','Long break'][t.phase]).encode()
            v.host_label=('Ready for next' if t.alert else ('Running' if t.running else 'Paused' if t.remaining_ms<duration else 'Ready')+f'  {t.completed}/4 done').encode()
            v.timer_progress=(duration-t.remaining_ms)*100//duration
            v.footer=('Press for next' if t.alert else ['Press start / pause','Press next session','Press reset cycle'][self.navigation.cursor] if page=='Focus' else 'Press for menu').encode()
            quiet=self.system_motion or bool(c.reduced_motion) or (self.battery<=10 and not self.usb)
            v.alert_pulse=timer_pulse(C.byref(t),self.now(),quiet)
        pet_frame=pet_get_frame(C.byref(self.pet),self.now(),not bool(b.animation_fps))
        v.pet_wpm=pet_frame.wpm;v.pet_mode=pet_frame.mode;v.pet_frame=pet_frame.frame;v.pet_effect=pet_frame.effect;v.pet_phase=pet_frame.phase;v.pet_bob=pet_frame.bob
        if v.home and c.face==3 and self.timer.running:
            seconds=(self.timer.remaining_ms+999)//1000
            v.footer=f'{["Focus","Break","Long break"][self.timer.phase]} {seconds//60:02}:{seconds%60:02}'.encode()
        context_id=self.navigation.page+16*int(self.state.control_layer)+32*self.state.pairing+128*b.stage
        motion_update(C.byref(self.motion),context_id,v.selected,self.direction,self.now(),not bool(b.animation_fps))
        motion_apply(C.byref(self.motion),C.byref(v));v.editing=bool(self.navigation.editing)
        self.display_fps=30 if motion_active(C.byref(self.motion)) and b.animation_fps else b.animation_fps if v.home else 0
        if self.timer.alert and ((self.now()-self.timer.finished_at)&0xffffffff)<4000 and not (self.system_motion or c.reduced_motion or (self.battery<=10 and not self.usb)):self.display_fps=max(self.display_fps,2)
        # Status fields always come from the C state, rather than the client view.
        v.status_left=HOSTS[self.state.config.active_host].upper().encode();v.status_right=f'{self.battery}%'.encode()
        v.os=[b'MAC',b'WIN',b'AND'][self.state.config.os[self.state.config.active_host]]
        screen_color=self.aux.get('screenColor')
        if isinstance(screen_color,str) and re.fullmatch(r'#[0-9a-fA-F]{6}',screen_color):
            r,g,b=bytes.fromhex(screen_color[1:]);v.accent=((r>>3)<<11)|((g>>2)<<5)|(b>>3);v.custom_accent=True
        v.os_source=0 if self.state.config.os_auto_mask&(1<<self.state.config.active_host) else 2
        pixels=(C.c_uint16*1024)();rgb=bytearray()
        for y in range(0,128,8):
            if not render_tile(C.byref(v),y,8,pixels,1024):raise ValueError('C tile render failed')
            for p in pixels:rgb.extend((((p>>11)&31)*255//31,((p>>5)&63)*255//63,(p&31)*255//31))
        return base64.b64encode(png(bytes(rgb))).decode()
    def power_budget(self):
        state=State.from_buffer_copy(self.state)
        if self.system_motion:state.config.reduced_motion=1
        return timer_budget(C.byref(self.timer),budget(C.byref(state),self.now(),self.battery,self.usb))
    def snapshot(self,view=None):
        self.tick_all();s=self.state;b=self.power_budget()
        if s.pairing==3:self.error='No host found. Try pairing again.'
        if view:self.last_view=view
        result={'sequence':self.seq,'config':self.config_json(),'connected':HOSTS[s.connected_slot] if s.connected_slot<5 else None,
            'page':PAGES[self.navigation.page],'cursor':self.navigation.cursor,'volume':self.navigation.volume,'editing':bool(self.navigation.editing),'wheelDivisor':self.navigation.wheel_divisor,
            'control':s.control_layer,'pairing':{'id':HOSTS[s.pair_slot],'remaining':max(0,30000-(self.now()-s.pair_started))} if s.pairing==2 else None,
            'confirm':{'type':'pair','id':HOSTS[s.pair_slot],'replacing':bool(s.config.bonded_mask&(1<<s.pair_slot))} if s.pairing==1 else None,
            'error':self.error,'power':{'stage':['active','dim','off','sleep'][b.stage],'rgb':b.rgb,'screen':b.screen,'fps':b.animation_fps},
            'mappings':{'caps':map_usage(C.byref(s),0x39),'leftCtrl':map_usage(C.byref(s),0xe0),'leftAlt':map_usage(C.byref(s),0xe2),'leftWin':map_usage(C.byref(s),0xe3)},
            'backend':'compiled C core + RGB565 tile renderer','releaseEpoch':s.release_epoch}
        pixels=(U8*270)();light_config=Config.from_buffer_copy(s.config)
        light_config.reduced_motion=bool(light_config.reduced_motion or not b.animation_fps)
        lighting_frame(C.byref(light_config),b.rgb,self.now(),pixels)
        result['lightingColors']={key:'#'+''.join(f'{pixels[ch*90+row*15+col]*255//127:02x}' for ch in range(3)) for key,row,col in RGB_COORDINATES}
        result['lightingFps']=30 if b.rgb and b.animation_fps and light_config.effect else 0
        result['timer']={'phase':['Focus','Short break','Long break'][self.timer.phase],'remaining':(self.timer.remaining_ms+999)//1000,'remainingMs':self.timer.remaining_ms,'running':bool(self.timer.running),'alert':bool(self.timer.alert),'completed':self.timer.completed,'pulse':bool(timer_pulse(C.byref(self.timer),self.now(),self.system_motion or bool(s.config.reduced_motion) or (self.battery<=10 and not self.usb)))}
        pf=pet_get_frame(C.byref(self.pet),self.now(),not bool(b.animation_fps))
        result['pet']={'mode':['Idle','Typing','Flow','Zoom','Sleepy'][pf.mode],'wpm':pf.wpm,'frame':pf.frame,'effect':['None','Sparkles','Hearts','Confetti','Speed lines'][pf.effect],'effectId':pf.effect,'phase':pf.phase,'bob':pf.bob,'quiet':not bool(b.animation_fps)}
        if self.last_view:result['frame']=self.frame(self.last_view)
        result['motion']={'active':bool(motion_active(C.byref(self.motion))),'highlight':self.motion.selection/256,'slide':self.motion.slide/256,'fps':self.display_fps}
        return result

RGB_COORDINATES=[(str(x['vendor_key']['key_index']),x['sense_bit'],x['scan_index']) for x in json.loads((ROOT/'firmware/targets/f75max/board-map.json').read_text())['matrix']['coordinates'] if x.get('vendor_key')]
SESSIONS={};LOCK=threading.Lock()
def maintain_timers():
    while True:
        with LOCK:sessions=list(SESSIONS.values())
        for session in sessions:
            with session.lock:session.tick_all()
        time.sleep(.25)
class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*args,**kwargs):super().__init__(*args,directory=str(ROOT/'ui'),**kwargs)
    def log_message(self,fmt,*args):
        if self.path.startswith('/api/'):return
        print(time.strftime('%Y-%m-%dT%H:%M:%S'),fmt%args,flush=True)
    def session(self):
        sid=None
        for item in self.headers.get('Cookie','').split(';'):
            if item.strip().startswith('f75sid='):sid=item.strip().split('=',1)[1]
        with LOCK:
            if sid not in SESSIONS:
                if len(SESSIONS)>32:raise ValueError('Preview session limit reached')
                sid=sid if isinstance(sid,str) and re.fullmatch(r'[0-9a-f]{32}',sid) else secrets.token_hex(16)
                SESSIONS[sid]=Session(sid)
            return SESSIONS[sid]
    def respond(self,obj,session,status=200):
        data=json.dumps(obj,separators=(',',':')).encode();self.send_response(status)
        self.send_header('Content-Type','application/json');self.send_header('Cache-Control','no-store')
        self.send_header('Set-Cookie',f'f75sid={session.sid}; HttpOnly; SameSite=Strict; Path=/')
        self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
    def do_GET(self):
        if self.path=='/api/hardware':
            from hardware_api import handle
            handle(self);return
        if self.path=='/api/state':
            session=self.session()
            with session.lock:self.respond(session.snapshot(),session)
        else:super().do_GET()
    def do_POST(self):
        if self.path=='/api/hardware':
            from hardware_api import handle
            handle(self);return
        origin=self.headers.get('Origin')
        if origin and origin!='http://'+self.headers.get('Host',''):
            self.send_error(403);return
        try:
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<=65536:raise ValueError('Invalid request size')
            body=json.loads(self.rfile.read(length));session=self.session()
            with session.lock:
                seq=body.get('sequence',0)
                if isinstance(seq,int) and seq>session.seq:
                    commands=body.get('commands',[])
                    if not isinstance(commands,list) or len(commands)>150:raise ValueError('Too many commands')
                    if not body.get('explicitSettings'):session.update_visual_settings(body.get('config'))
                    session.battery=max(1,min(100,int(body.get('battery',78))));session.usb=bool(body.get('charging'));session.system_motion=bool(body.get('systemReducedMotion'))
                    for command in commands:session.command(command['name'],command.get('args',[]))
                    session.seq=seq
                self.respond(session.snapshot(body.get('view')),session)
        except (ValueError,TypeError,KeyError,IndexError) as exc:self.send_error(400,str(exc))

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--bind',required=True);parser.add_argument('--port',type=int,default=8765);args=parser.parse_args()
    print('F75 Studio started; bind='+args.bind+' port='+str(args.port)+' preview=simulated hardware_editor=raw_hid',flush=True)
    threading.Thread(target=maintain_timers,name='f75-timer-clock',daemon=True).start()
    ThreadingHTTPServer((args.bind,args.port),Handler).serve_forever()
if __name__=='__main__':main()
