// SPDX-License-Identifier: GPL-2.0-or-later
#include "f75_bundle.h"
#include <string.h>
static void put32(uint8_t *p,uint32_t v){for(unsigned i=0;i<4;++i)p[i]=v>>(i*8);}
static uint32_t get32(const uint8_t *p){return (uint32_t)p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);}
void f75_bundle_encode(const f75_config *c,const f75_custom *x,uint8_t out[F75_BUNDLE_BYTES]){
    f75_record_encode(c,0,out);f75_custom_encode(x,out+F75_RECORD_BYTES);
}
bool f75_bundle_decode(const uint8_t in[F75_BUNDLE_BYTES],f75_config *c,f75_custom *x){
    uint32_t ignored;return f75_record_decode(in,c,&ignored)&&f75_custom_decode(in+F75_RECORD_BYTES,x);
}
void f75_envelope_encode(const f75_config *c,const f75_custom *x,uint32_t gen,uint8_t out[F75_ENVELOPE_BYTES]){
    memset(out,0xff,F75_ENVELOPE_BYTES);memcpy(out,"F75X",4);put32(out+4,1);put32(out+8,F75_ENVELOPE_BYTES);put32(out+12,gen);
    f75_bundle_encode(c,x,out+16);put32(out+F75_ENVELOPE_BYTES-4,f75_crc32(out,F75_ENVELOPE_BYTES-4));
}
bool f75_envelope_decode(const uint8_t in[F75_ENVELOPE_BYTES],f75_config *c,f75_custom *x,uint32_t *gen){
    if(memcmp(in,"F75X",4)||get32(in+4)!=1||get32(in+8)!=F75_ENVELOPE_BYTES||
       get32(in+F75_ENVELOPE_BYTES-4)!=f75_crc32(in,F75_ENVELOPE_BYTES-4))return false;
    if(!f75_bundle_decode(in+16,c,x))return false;
    *gen=get32(in+12);return true;
}
