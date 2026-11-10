// SPDX-License-Identifier: GPL-2.0-or-later
#include "f75_transfer.h"
#include <string.h>
static uint16_t get16(const uint8_t *p){return (uint16_t)p[0]|((uint16_t)p[1]<<8);}
static uint32_t get32(const uint8_t *p){uint32_t v=0;for(unsigned i=0;i<4;++i)v|=(uint32_t)p[i]<<(8*i);return v;}
static void put32(uint8_t *p,uint32_t v){for(unsigned i=0;i<4;++i)p[i]=v>>(8*i);}
bool f75_transfer_receive(f75_transfer *t,const uint8_t q[32],uint8_t r[32],uint32_t now,const f75_config *c,const f75_custom *x){
    if(memcmp(q,"F75u",4))return false;
    memset(r,0,32);memcpy(r,"F75t",4);memcpy(r+4,q+4,4);
    uint32_t token=get32(q+8);uint8_t op=q[12],status=0;uint16_t offset=get16(q+13);
    if((t->phase==1||t->phase==2)&&now-t->touched>20000u){t->phase=0;t->token=0;t->next=0;}
    if(op==0){r[15]=1;r[16]=F75_BUNDLE_BYTES&255;r[17]=F75_BUNDLE_BYTES>>8;r[18]=t->phase;r[19]=t->save;}
    else if(op==1||op==4){
        if(t->phase==1||t->phase==2||t->phase==3)status=1;
        else if(!token||(op==1&&offset!=F75_BUNDLE_BYTES))status=3;
        else{t->token=token;t->next=0;t->save=false;t->touched=now;t->phase=op==1?1:2;
            if(op==1)t->expected_crc=get32(q+15);else f75_bundle_encode(c,x,t->bytes);}
    }else if(!token||token!=t->token)status=4;
    else if(op==2){
        if(t->phase!=1)status=1;
        else if(offset!=t->next||offset>=F75_BUNDLE_BYTES)status=3;
        else{unsigned n=F75_BUNDLE_BYTES-offset;if(n>17)n=17;memcpy(t->bytes+offset,q+15,n);t->next+=n;t->touched=now;}
    }else if(op==3){
        if(t->phase!=1)status=1;
        else if(t->next!=F75_BUNDLE_BYTES||offset!=F75_BUNDLE_BYTES||(q[15]&~1u))status=3;
        else if(f75_crc32(t->bytes,F75_BUNDLE_BYTES)!=t->expected_crc){status=2;t->phase=6;}
        else {t->save=q[15]&1u;t->phase=3;}
    }else if(op==5){
        if(t->phase!=2)status=1;
        else if(offset>=F75_BUNDLE_BYTES)status=3;
        else{unsigned n=F75_BUNDLE_BYTES-offset;if(n>17)n=17;memcpy(r+15,t->bytes+offset,n);t->touched=now;}
    }else if(op==6){
        if(t->phase==3)status=1;
        else {t->phase=0;t->token=0;t->next=0;}
    }else status=3;
    put32(r+8,t->token);r[12]=status;r[13]=t->next;r[14]=t->next>>8;return true;
}
