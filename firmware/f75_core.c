#include "f75_core.h"
static void copy_bytes(void *destination,const void *source,size_t n){uint8_t *d=destination;const uint8_t *s=source;while(n--)*d++=*s++;}
static void clear_bytes(void *destination,size_t n){uint8_t *d=destination;while(n--)*d++=0;}
static bool same_bytes(const void *a,const void *b,size_t n){const uint8_t *x=a,*y=b;while(n--)if(*x++!=*y++)return false;return true;}
static bool has_zero(const char *p,size_t n){while(n--)if(!*p++)return true;return false;}

static uint8_t minimum(uint8_t a, uint8_t b) { return a < b ? a : b; }
static const uint8_t color_presets[6][3]={{0x91,0xe2,0xce},{0xf2,0xa4,0xaa},{0xc4,0xb4,0xef},{0xa4,0xc8,0xf2},{0xed,0xc0,0x8c},{255,255,255}};
static unsigned color_index(const f75_config *c){for(unsigned i=0;i<6;i++)if(same_bytes(c->color,color_presets[i],3))return i;return 6;}
const char *f75_color_name(const f75_config *c){static const char *names[]={"Mint","Rose","Lilac","Ocean","Peach","White","Custom"};return names[color_index(c)];}
void f75_cycle_color(f75_config *c){unsigned i=color_index(c);copy_bytes(c->color,color_presets[i<5?i+1:0],3);}
static void put32(uint8_t *p, uint32_t v) { for (unsigned i=0;i<4;i++) p[i]=(uint8_t)(v>>(i*8)); }
static uint32_t get32(const uint8_t *p) { return (uint32_t)p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24); }
uint32_t f75_crc32(const uint8_t *p, size_t n) {
    uint32_t crc=UINT32_MAX;
    while(n--) { crc^=*p++; for(unsigned bit=0;bit<8;bit++) crc=(crc>>1)^(UINT32_C(0xedb88320)&(0u-(crc&1u))); }
    return crc^UINT32_MAX;
}
static uint32_t next_transaction(f75_state *s) { if (++s->transaction==0) ++s->transaction; return s->transaction; }
void f75_defaults(f75_config *c) {
    static const char names[F75_HOSTS][19]={"USB cable","Laptop","Device 2","Device 3","Receiver"};
    clear_bytes(c,sizeof(*c)); copy_bytes(c->names,names,sizeof(names));
    c->os[2]=c->os[4]=F75_WINDOWS; c->caps_swap=1;
    c->brightness=28; c->speed=35; c->effect=0;c->face=3;
    c->color[0]=0x91;c->color[1]=0xe2;c->color[2]=0xce;
    c->os_auto_mask=0x1f;
}
bool f75_config_valid(const f75_config *c) {
    if(c->active_host>=F75_HOSTS||c->caps_swap>1||c->power>F75_DESK||c->brightness>100||c->speed>100||c->effect>4||c->wheel>2||c->face>3||c->reduced_motion>1||c->light_mode>1||(c->bonded_mask&0xe0)||(c->os_auto_mask&0xe0)) return false;
    for(unsigned i=0;i<F75_HOSTS;i++) if(c->os[i]>F75_ANDROID||!c->names[i][0]||!has_zero(c->names[i],sizeof(c->names[i]))) return false;
    return true;
}
void f75_init(f75_state *s,const f75_config *c,uint32_t now) {
    clear_bytes(s,sizeof(*s)); if(c&&f75_config_valid(c))copy_bytes(&s->config,c,sizeof(*c));else f75_defaults(&s->config);
    s->last_activity=now; s->connected_slot=UINT8_MAX;
}
uint16_t f75_map_usage(const f75_state *s,uint16_t usage) {
    if(s->config.caps_swap) { if(usage==0x39)usage=0xe0;else if(usage==0xe0)usage=0x39; }
    if(s->config.os[s->config.active_host]==F75_MAC) {
        if(usage==0xe0)return 0xe3;
        if(usage==0xe4)return 0xe7;
        if(usage==0xe2)return 0xe3;
        if(usage==0xe3)return 0xe2;
        if(usage==0xe6)return 0xe7;
        if(usage==0xe7)return 0xe6;
    }
    return usage;
}
bool f75_set_os(f75_state *s,f75_os os) {
    if(os!=F75_MAC&&os!=F75_WINDOWS&&os!=F75_ANDROID)return false;
    s->config.os_auto_mask&=(uint8_t)~(1u<<s->config.active_host);
    if(s->config.os[s->config.active_host]!=(uint8_t)os){s->release_epoch++;s->config.os[s->config.active_host]=(uint8_t)os;}
    return true;
}
bool f75_detect_os(f75_state *s,uint8_t slot,f75_os os){
    if(slot>=F75_HOSTS||(os!=F75_MAC&&os!=F75_WINDOWS&&os!=F75_ANDROID)||!(s->config.os_auto_mask&(1u<<slot)))return false;
    if(s->config.os[slot]!=(uint8_t)os){s->config.os[slot]=os;if(s->config.active_host==slot)++s->release_epoch;}
    return true;
}
bool f75_host_os_hint(f75_state *s,uint8_t slot,f75_os os,uint32_t transaction,bool connected){
    /* USB-host knowledge must never leak into another wireless host. The
     * helper supplies local-device evidence; this guard rejects a stale
     * connection, a route change, pairing, and every manual override. */
    if(!connected||slot<1||slot>4||slot!=s->config.active_host||
       !transaction||transaction!=s->transaction||s->pairing!=F75_PAIR_IDLE)return false;
    return f75_detect_os(s,slot,os);
}
void f75_set_caps_swap(f75_state *s,bool enabled) { if(s->config.caps_swap!=(uint8_t)enabled){s->release_epoch++;s->config.caps_swap=(uint8_t)enabled;} }
void f75_set_control_layer(f75_state *s,bool enabled) { if(s->control_layer!=enabled){s->release_epoch++;s->control_layer=enabled;} }
void f75_activity(f75_state *s,uint32_t now) { s->last_activity=now; }
uint32_t f75_switch_host(f75_state *s,uint8_t slot,uint32_t now) {
    if(slot>=F75_HOSTS||s->pairing==F75_PAIR_WAIT||s->pairing==F75_PAIR_CONFIRM)return 0;
    s->release_epoch++;s->config.active_host=slot;s->connected_slot=UINT8_MAX;s->last_activity=now;
    return next_transaction(s);
}
bool f75_pair_request(f75_state *s,uint8_t slot,uint32_t now) {
    if(slot<1||slot>3||s->pairing==F75_PAIR_WAIT||s->pairing==F75_PAIR_CONFIRM)return false;
    s->pair_slot=slot;s->pairing=F75_PAIR_CONFIRM;s->last_activity=now;return true;
}
uint32_t f75_pair_confirm(f75_state *s,uint32_t held_ms,uint32_t now) {
    if(s->pairing!=F75_PAIR_CONFIRM||held_ms<1200)return 0;
    s->pairing=F75_PAIR_WAIT;s->pair_started=now;s->last_activity=now;s->release_epoch++;
    return next_transaction(s);
}
bool f75_host_ack(f75_state *s,uint8_t slot,uint32_t transaction) {
    if(!transaction||transaction!=s->transaction||slot>=F75_HOSTS)return false;
    if(s->pairing==F75_PAIR_WAIT){
        if(slot!=s->pair_slot)return false;
        s->config.bonded_mask|=(uint8_t)(1u<<slot);s->config.active_host=slot;s->pairing=F75_PAIR_IDLE;
    }else if(s->pairing!=F75_PAIR_IDLE||slot!=s->config.active_host)return false;
    s->connected_slot=slot;return true;
}
void f75_pair_cancel(f75_state *s) { s->pairing=F75_PAIR_IDLE;next_transaction(s); }
void f75_tick(f75_state *s,uint32_t now) {
    if(s->pairing==F75_PAIR_WAIT&&(uint32_t)(now-s->pair_started)>=30000){s->pairing=F75_PAIR_TIMEOUT;s->last_activity=now;next_transaction(s);}
}
f75_budget f75_power_budget(const f75_state *s,uint32_t now,uint8_t battery,bool usb) {
    static const uint32_t dim[]={15000,8000,60000},off[]={45000,25000,180000},sleep[]={180000,90000,600000};
    static const uint8_t caps[]={40,18,75},screens[]={65,40,85},fps[]={12,8,20};
    unsigned p=s->config.power;uint32_t idle=now-s->last_activity;
    f75_budget b={F75_ACTIVE,minimum(s->config.brightness,usb?100:caps[p]),screens[p],fps[p]};
    if(s->pairing!=F75_PAIR_WAIT&&s->pairing!=F75_PAIR_CONFIRM){
        if(idle>=sleep[p])b.stage=F75_SLEEP;else if(idle>=off[p])b.stage=F75_OFF;else if(idle>=dim[p])b.stage=F75_DIM;
    }
    if(!usb&&battery<=10){b.rgb=minimum(b.rgb,8);b.screen=minimum(b.screen,25);b.animation_fps=0;}
    if(!usb&&battery<=5){b.rgb=0;b.screen=10;}
    if(s->config.reduced_motion)b.animation_fps=0;
    if(b.stage==F75_DIM){b.rgb=minimum(b.rgb,4);b.screen=minimum(b.screen,16);b.animation_fps=0;}
    if(b.stage>=F75_OFF)b.rgb=b.screen=b.animation_fps=0;
    return b;
}
void f75_record_encode(const f75_config *c,uint32_t generation,uint8_t out[F75_RECORD_BYTES]) {
    clear_bytes(out,F75_RECORD_BYTES);copy_bytes(out,"F75S",4);out[4]=5;out[6]=F75_RECORD_BYTES;put32(out+8,generation);
    copy_bytes(out+12,c->os,F75_HOSTS);copy_bytes(out+17,c->names,sizeof(c->names));
    const uint8_t fields[]={c->active_host,c->bonded_mask,c->caps_swap,c->power,c->brightness,c->speed,c->effect,c->wheel,c->face,c->reduced_motion,c->color[0],c->color[1],c->color[2]};
    copy_bytes(out+112,fields,sizeof(fields));out[125]=c->light_mode;out[126]=c->os_auto_mask;put32(out+156,f75_crc32(out,156));
}
bool f75_record_decode(const uint8_t in[F75_RECORD_BYTES],f75_config *c,uint32_t *generation) {
    if(!same_bytes(in,"F75S",4)||in[4]<1||in[4]>5||in[6]!=F75_RECORD_BYTES||in[7]||get32(in+156)!=f75_crc32(in,156))return false;
    f75_config candidate;clear_bytes(&candidate,sizeof(candidate));copy_bytes(candidate.os,in+12,F75_HOSTS);copy_bytes(candidate.names,in+17,sizeof(candidate.names));
    if(in[4]<5)for(unsigned i=0;i<F75_HOSTS;i++)if(candidate.os[i]>F75_WINDOWS)return false;
    candidate.active_host=in[112];candidate.bonded_mask=in[113];candidate.caps_swap=in[114];candidate.power=in[115];candidate.brightness=in[116];candidate.speed=in[117];candidate.effect=in[118];candidate.wheel=in[119];candidate.face=in[120];candidate.reduced_motion=in[121];copy_bytes(candidate.color,in+122,3);
    candidate.light_mode=in[4]>=2?in[125]:0;
    candidate.os_auto_mask=in[4]>=4?in[126]:0;
    if(in[4]<3&&candidate.face==0)candidate.face=3;
    if(!f75_config_valid(&candidate))return false;
    copy_bytes(c,&candidate,sizeof(candidate));
    if(generation)*generation=get32(in+8);
    return true;
}
bool f75_record_select(const uint8_t a[F75_RECORD_BYTES],const uint8_t b[F75_RECORD_BYTES],f75_config *c,uint32_t *generation) {
    f75_config ca,cb;uint32_t ga=0,gb=0;bool va=f75_record_decode(a,&ca,&ga),vb=f75_record_decode(b,&cb,&gb);
    if(!va&&!vb)return false;
    bool choose_b=vb&&(!va||(gb!=ga&&(uint32_t)(gb-ga)<UINT32_C(0x80000000)));
    copy_bytes(c,choose_b?&cb:&ca,sizeof(*c));if(generation)*generation=choose_b?gb:ga;return true;
}
