#include "f75_route.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
int main(void){
 uint8_t pages[2048],entry[16];memset(pages,255,sizeof(pages));assert(!f75_route_latest(pages).valid);
 for(unsigned change=0;change<300;++change){
  uint8_t slot=(uint8_t)(1+change%3);unsigned offset;bool erase;uint32_t sequence;
  assert(f75_route_plan(pages,slot,&offset,&erase,&sequence));
  f75_route_record old=f75_route_latest(pages);
  if(erase){assert(!old.valid||offset/1024!=old.offset/1024);memset(pages+offset,255,1024);assert(f75_route_latest(pages).sequence==old.sequence);}
  f75_route_encode(entry,sequence,slot);
  for(unsigned cut=0;cut<16;cut++){
   memcpy(pages+offset,entry,cut);memset(pages+offset+cut,255,16-cut);
   f75_route_record latest=f75_route_latest(pages);if(!memcmp(pages+offset,entry,16)){assert(latest.valid&&latest.slot==slot&&latest.sequence==sequence);continue;}
   assert(latest.valid==old.valid);
   if(old.valid)assert(latest.sequence==old.sequence&&latest.slot==old.slot);
  }
  memcpy(pages+offset,entry,16);f75_route_record r=f75_route_latest(pages);assert(r.valid&&r.slot==slot&&r.sequence==change+1);
  assert(!f75_route_plan(pages,slot,&offset,&erase,&sequence));
 }
 memset(pages,255,sizeof(pages));f75_route_encode(pages,UINT32_MAX,2);f75_route_encode(pages+16,0,3);assert(f75_route_latest(pages).slot==3);
 pages[16+12]^=1;assert(f75_route_latest(pages).slot==2);
 assert(!f75_route_plan(pages,0,(unsigned[]){0},(bool[]){0},(uint32_t[]){0}));
 puts("Bluetooth route journal: append, rollover, every torn-write prefix, CRC, duplicate suppression and sequence wrap passed.");
}
