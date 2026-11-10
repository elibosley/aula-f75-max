// SPDX-License-Identifier: GPL-2.0-or-later
#include "f75_custom.h"
#include <string.h>
static void put16(uint8_t *p,uint16_t v){p[0]=v;p[1]=v>>8;}
static uint16_t get16(const uint8_t *p){return (uint16_t)p[0]|((uint16_t)p[1]<<8);}
static void put32(uint8_t *p,uint32_t v){for(unsigned i=0;i<4;++i)p[i]=v>>(8*i);}
static uint32_t get32(const uint8_t *p){uint32_t v=0;for(unsigned i=0;i<4;++i)v|=(uint32_t)p[i]<<(8*i);return v;}
static bool key_usage(uint16_t usage){return (usage>=4&&usage<=0xe7)||usage==F75_MACRO_PRIMARY;}
static bool binding(uint16_t usage){
    return !usage||usage==F75_BIND_DISABLED||(usage>=4&&usage<=0xe7)||
        (usage>=F75_BIND_MACRO&&usage<F75_BIND_MACRO+F75_CUSTOM_MACROS)||
        (usage>F75_BIND_CONSUMER&&usage<F75_BIND_CONSUMER+0x1000)||
        usage==F75_BIND_SCROLL_UP||usage==F75_BIND_SCROLL_DOWN||
        (usage>=F75_BIND_MOUSE_LEFT&&usage<=F75_BIND_MOUSE_MIDDLE);
}
void f75_custom_defaults(f75_custom *c){memset(c,0,sizeof(*c));}
bool f75_custom_valid(const f75_custom *c){
    if(!c||(c->layer_mask&~7u)||c->screen_custom>1)return false;
    for(unsigned layer=0;layer<2;++layer)for(unsigned key=0;key<F75_CUSTOM_KEYS;++key){
        uint16_t v=c->keys[layer][key];if(!binding(v))return false;
        if((key==71||key==84)&&v)return false; /* physical Fn and wheel/recovery */
        if(layer==1&&v&&(key==0||key==7||key==13||key==19||key==25||key==31||key==41||key==52||key==62))return false;
        if(v>=F75_BIND_MACRO&&v<F75_BIND_MACRO+F75_CUSTOM_MACROS&&!c->macro_length[v-F75_BIND_MACRO])return false;
    }
    for(unsigned layer=0;layer<F75_CUSTOM_LAYERS;++layer)for(unsigned key=0;key<F75_CUSTOM_KEYS;++key)if(c->colored[layer][key]>1)return false;
    for(unsigned slot=0;slot<F75_CUSTOM_MACROS;++slot){
        if(c->macro_length[slot]>F75_MACRO_STEPS||c->macro_repeat[slot]>1)return false;
        /* Primary aliases a real modifier. Validate both host mappings so a
         * macro cannot release Command/Ctrl while another step owns it. */
        for(unsigned os=0;os<2;++os){
        uint8_t held[32]={0};unsigned duration=0,simultaneous=0;
        for(unsigned i=0;i<c->macro_length[slot];++i){
            f75_macro_step s=c->steps[slot][i];uint16_t usage=s.usage&~F75_MACRO_UP;
            if(s.delay_ms>5000u||(duration+=s.delay_ms)>120000u)return false;
            if(!usage){if(s.usage)return false;continue;}
            if(!key_usage(usage))return false;
            if(usage==F75_MACRO_PRIMARY)usage=os==F75_MAC?0xe3:0xe0;
            unsigned byte=usage/8,mask=1u<<(usage&7);
            if(s.usage&F75_MACRO_UP){if(!(held[byte]&mask))return false;held[byte]&=~mask;if(usage<0xe0)--simultaneous;}
            else {if(held[byte]&mask)return false;held[byte]|=mask;if(usage<0xe0&&++simultaneous>6)return false;}
        }
        for(unsigned i=0;i<sizeof(held);++i)if(held[i])return false;
        }
    }
    return true;
}
void f75_custom_encode(const f75_custom *c,uint8_t out[F75_CUSTOM_BYTES]){
    memset(out,0,F75_CUSTOM_BYTES);memcpy(out,"F75C",4);out[4]=c->screen_custom?2:1;put16(out+6,F75_CUSTOM_BYTES);
    unsigned at=16;
    for(unsigned layer=0;layer<2;++layer)for(unsigned key=0;key<F75_CUSTOM_KEYS;++key){put16(out+at,c->keys[layer][key]);at+=2;}
    memcpy(out+at,c->colors,sizeof(c->colors));at+=sizeof(c->colors);
    memcpy(out+at,c->colored,sizeof(c->colored));at+=sizeof(c->colored);
    memcpy(out+at,c->layer_colors,sizeof(c->layer_colors));at+=sizeof(c->layer_colors);out[at++]=c->layer_mask;
    memcpy(out+at,c->macro_length,8);at+=8;memcpy(out+at,c->macro_repeat,8);at+=8;
    for(unsigned slot=0;slot<8;++slot)for(unsigned step=0;step<32;++step){
        put16(out+at,c->steps[slot][step].usage);put16(out+at+2,c->steps[slot][step].delay_ms);at+=4;
    }
    if(c->screen_custom){out[2512]=1;memcpy(out+2513,c->screen_color,3);}
    put32(out+F75_CUSTOM_BYTES-4,f75_crc32(out,F75_CUSTOM_BYTES-4));
}
bool f75_custom_decode(const uint8_t in[F75_CUSTOM_BYTES],f75_custom *c){
    if(memcmp(in,"F75C",4)||(in[4]!=1&&in[4]!=2)||get16(in+6)!=F75_CUSTOM_BYTES||get32(in+F75_CUSTOM_BYTES-4)!=f75_crc32(in,F75_CUSTOM_BYTES-4))return false;
    memset(c,0,sizeof(*c));
    unsigned at=16;
    for(unsigned layer=0;layer<2;++layer)for(unsigned key=0;key<F75_CUSTOM_KEYS;++key){c->keys[layer][key]=get16(in+at);at+=2;}
    memcpy(c->colors,in+at,sizeof(c->colors));at+=sizeof(c->colors);
    memcpy(c->colored,in+at,sizeof(c->colored));at+=sizeof(c->colored);
    memcpy(c->layer_colors,in+at,sizeof(c->layer_colors));at+=sizeof(c->layer_colors);c->layer_mask=in[at++];
    memcpy(c->macro_length,in+at,8);at+=8;memcpy(c->macro_repeat,in+at,8);at+=8;
    for(unsigned slot=0;slot<8;++slot)for(unsigned step=0;step<32;++step){c->steps[slot][step].usage=get16(in+at);c->steps[slot][step].delay_ms=get16(in+at+2);at+=4;}
    if(in[4]>=2){c->screen_custom=in[2512];memcpy(c->screen_color,in+2513,3);}
    return f75_custom_valid(c);
}
uint16_t f75_custom_binding(const f75_custom *c,uint8_t key,bool fn,uint16_t stock){
    if(key>=90)return stock;
    uint16_t value=c->keys[fn?1:0][key];if(!value&&fn)value=c->keys[0][key];return value?value:stock;
}
void f75_custom_lighting(const f75_custom *c,uint8_t layer,uint8_t brightness,uint8_t pwm[270]){
    if(layer>=3)layer=0;
    unsigned peak=(brightness>100?100:brightness)*127u/100u;
    bool flat=(c->layer_mask&(1u<<layer))!=0;
    for(unsigned key=0;key<90;++key){
        const uint8_t *color=flat?c->layer_colors[layer]:NULL;
        if(c->colored[layer][key])color=c->colors[layer][key];
        else if(!flat&&c->colored[0][key])color=c->colors[0][key];
        if(color){unsigned led=(key%6)*15+key/6;for(unsigned ch=0;ch<3;++ch)pwm[ch*90+led]=(uint8_t)((unsigned)color[ch]*peak/255u);}
    }
}
void f75_macro_cancel(f75_macro_player *p,f75_macro_emit emit,void *context){
    for(unsigned usage=4;usage<=0xe7;++usage)if(p->held[usage/8]&(1u<<(usage&7)))emit(context,(uint16_t)usage,false);
    memset(p,0,sizeof(*p));
}
bool f75_macro_start(f75_macro_player *p,const f75_custom *c,uint8_t slot,f75_os os,uint32_t now,f75_macro_emit emit,void *context){
    if(slot>=8||!c->macro_length[slot]||c->macro_length[slot]>32)return false;
    f75_macro_cancel(p,emit,context);p->active=true;p->slot=slot;p->os=(uint8_t)os;p->repeat=c->macro_repeat[slot];p->due=now+c->steps[slot][0].delay_ms;return true;
}
void f75_macro_release(f75_macro_player *p){p->repeat=false;}
void f75_macro_tick(f75_macro_player *p,const f75_custom *c,uint32_t now,uint16_t gap,f75_macro_emit emit,void *context){
    if(!p->active||(int32_t)(now-p->due)<0)return;
    f75_macro_step s=c->steps[p->slot][p->step];uint16_t usage=s.usage&~F75_MACRO_UP;
    if(usage==F75_MACRO_PRIMARY)usage=p->os==F75_MAC?0xe3:0xe0;
    if(usage){unsigned mask=1u<<(usage&7);bool down=!(s.usage&F75_MACRO_UP);
        if(down)p->held[usage/8]|=mask;else p->held[usage/8]&=~mask;emit(context,usage,down);
    }
    if(++p->step==c->macro_length[p->slot]){
        if(!p->repeat){f75_macro_cancel(p,emit,context);return;}
        p->step=0;if(gap<20)gap=20;
    }
    p->due=now+gap+c->steps[p->slot][p->step].delay_ms;
}
