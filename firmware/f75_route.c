#include "f75_route.h"
#include "f75_core.h"
#include <string.h>
static uint32_t word(const uint8_t *p){return (uint32_t)p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);}
static void put(uint8_t *p,uint32_t x){for(unsigned i=0;i<4;i++)p[i]=(uint8_t)(x>>(8*i));}
f75_route_record f75_route_latest(const uint8_t *pages){
 f75_route_record best={0};
 for(unsigned at=0;at<F75_ROUTE_BYTES;at+=16){
  const uint8_t *p=pages+at;
  if(memcmp(p,"F75R",4)||word(p+8)<1||word(p+8)>3||word(p+12)!=f75_crc32(p,12))continue;
  uint32_t sequence=word(p+4);
  if(!best.valid||(sequence!=best.sequence&&(uint32_t)(sequence-best.sequence)<0x80000000u))best=(f75_route_record){sequence,at,(uint8_t)word(p+8),true};
 }
 return best;
}
void f75_route_encode(uint8_t out[16],uint32_t sequence,uint8_t slot){memcpy(out,"F75R",4);put(out+4,sequence);put(out+8,slot);put(out+12,f75_crc32(out,12));}
bool f75_route_plan(const uint8_t *pages,uint8_t slot,unsigned *offset,bool *erase,uint32_t *sequence){
 if(slot<1||slot>3)return false;
 f75_route_record last=f75_route_latest(pages);if(last.valid&&last.slot==slot)return false;
 unsigned page=last.valid?last.offset/F75_ROUTE_PAGE:0;
 *sequence=last.valid?last.sequence+1:1;
 for(unsigned at=page*F75_ROUTE_PAGE;at<(page+1)*F75_ROUTE_PAGE;at+=16){
  bool blank=true;for(unsigned i=0;i<16;i++)if(pages[at+i]!=255){blank=false;break;}
  if(blank){*offset=at;*erase=false;return true;}
 }
 *offset=(1-page)*F75_ROUTE_PAGE;*erase=true;return true;
}
