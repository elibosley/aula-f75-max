#include "f75_custom.h"
#include <assert.h>
#include <string.h>
int main(void){
 f75_custom c,d;uint8_t bytes[F75_CUSTOM_BYTES];char label[8];
 f75_custom_defaults(&c);assert(c.battery_decimals==1&&c.battery_full_soc==0);
 assert(f75_battery_estimate(&c,25387)==10000);
 c.battery_full_soc=25600;
 assert(f75_battery_estimate(&c,25387)==9917);
 assert(f75_battery_estimate(&c,25600)==10000);
 assert(f75_battery_estimate(&c,0)==0);
 assert(f75_battery_estimate(&c,65535)==65535);
 for(unsigned places=0;places<=2;++places){
  c.battery_decimals=places;f75_custom_encode(&c,bytes);assert(bytes[4]==4);
  assert(f75_custom_decode(bytes,&d));assert(d.battery_full_soc==25600&&d.battery_decimals==places);
  f75_battery_label(label,9917,places);assert(!strcmp(label,places==0?"99%":places==1?"99.2%":"99.17%"));
  f75_battery_label(label,10000,places);assert(!strcmp(label,places==0?"100%":places==1?"100.0%":"100.00%"));
 }
 f75_battery_label(label,9999,1);assert(!strcmp(label,"100.0%"));
 f75_battery_label(label,65535,2);assert(!strcmp(label,"--%"));
 for(unsigned raw=0,previous=0;raw<=25600;++raw){unsigned estimate=f75_battery_estimate(&c,raw);assert(estimate>=previous&&estimate<=10000);previous=estimate;}
 for(unsigned version=1;version<=3;++version){
  f75_custom_encode(&c,bytes);bytes[4]=version;memset(bytes+2524,0xff,3);
  uint32_t crc=f75_crc32(bytes,F75_CUSTOM_BYTES-4);memcpy(bytes+F75_CUSTOM_BYTES-4,&crc,4);
  assert(f75_custom_decode(bytes,&d));assert(d.battery_full_soc==0&&d.battery_decimals==1);
 }
 c.battery_full_soc=23039;assert(!f75_custom_valid(&c));c.battery_full_soc=25601;assert(!f75_custom_valid(&c));
 c.battery_full_soc=25600;c.battery_decimals=3;assert(!f75_custom_valid(&c));
 return 0;
}
