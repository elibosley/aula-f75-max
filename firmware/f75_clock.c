// SPDX-License-Identifier: GPL-2.0-or-later
#include "f75_clock.h"
#include <string.h>
bool f75_clock_set(f75_clock *c,uint32_t seconds,uint32_t now){
    if(seconds>=86400u)return false;
    c->seconds=seconds;c->tick=now;c->valid=true;return true;
}
void f75_clock_tick(f75_clock *c,uint32_t now){
    if(!c->valid)return;
    uint32_t elapsed=now-c->tick,seconds=elapsed/1000u;
    c->tick+=seconds*1000u;c->seconds=(c->seconds+seconds)%86400u;
}
void f75_clock_text(const f75_clock *c,char out[6]){
    if(!c->valid){memcpy(out,"--:--",6);return;}
    unsigned h=c->seconds/3600u,m=c->seconds/60u%60u;
    out[0]='0'+h/10;out[1]='0'+h%10;out[2]=':';out[3]='0'+m/10;out[4]='0'+m%10;out[5]=0;
}
