#include "f75_display.h"
#include "f75_custom.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
static void render(f75_view *v,uint16_t *out){for(unsigned y=0;y<128;y+=8)assert(f75_render_tile(v,y,8,out+y*128,1024));}
int main(void){
 static uint16_t first[16384],next[16384];
 for(unsigned theme=0;theme<2;++theme){
  f75_view v={.home=true,.face=3,.light_mode=theme,.status_left="BT2",.status_right="100%",.os="MAC",.link_state=F75_LINK_CONNECTED,.power_state=F75_POWER_BATTERY};
  render(&v,first);
  for(unsigned link=1;link<=4;++link){
   v.link_state=link;render(&v,next);
   assert(!memcmp(first+20*128,next+20*128,(128-20)*128*sizeof(uint16_t)));
   if(link!=F75_LINK_CONNECTED)assert(memcmp(first,next,20*128*sizeof(uint16_t)));
   /* Quiet connection feedback must not blink when the frame clock changes. */
   v.motion=false;v.animation_phase=99;render(&v,first);v.animation_phase=0;render(&v,next);assert(!memcmp(first,next,20*128*sizeof(uint16_t)));
   v.link_state=F75_LINK_CONNECTED;render(&v,first);
  }
  for(unsigned power=2;power<=3;++power){
   v.power_state=power;render(&v,next);assert(memcmp(first,next,20*128*sizeof(uint16_t)));
   /* Keep percentages, other header elements and artwork intact. */
   for(unsigned y=0;y<20;++y){assert(!memcmp(first+y*128,next+y*128,70*sizeof(uint16_t)));assert(!memcmp(first+y*128+94,next+y*128+94,34*sizeof(uint16_t)));}
   assert(!memcmp(first+20*128,next+20*128,(128-20)*128*sizeof(uint16_t)));
  }
  v.home=false;render(&v,first);v.link_state=F75_LINK_OFFLINE;v.power_state=F75_POWER_BATTERY;render(&v,next);assert(!memcmp(first,next,sizeof(first)));
 }
 f75_custom c,d;f75_custom_defaults(&c);uint8_t bytes[F75_CUSTOM_BYTES],pwm[270];
 f75_custom_encode(&c,bytes);assert(bytes[4]==1&&f75_custom_decode(bytes,&d)&&d.indicator_mask==3&&!d.indicators_custom);
 c.indicators_custom=1;c.indicator_mask=2;c.fn_color[0]=33;f75_custom_encode(&c,bytes);
 assert(bytes[4]==3&&f75_custom_decode(bytes,&d)&&!memcmp(&c,&d,sizeof(c)));
 c.indicator_mask=4;assert(!f75_custom_valid(&c));c.indicator_mask=3;
 for(unsigned caps=0;caps<2;++caps)for(unsigned fn=0;fn<2;++fn)for(unsigned brightness=0;brightness<=100;brightness+=50){
  memset(pwm,7,sizeof(pwm));f75_custom_indicators(&c,caps,fn,brightness,pwm);
  for(unsigned i=0;i<270;++i){unsigned led=i%90;if(led!=45&&led!=86)assert(pwm[i]==7);}
  unsigned peak=brightness*127u/100u;
  for(unsigned ch=0;ch<3;++ch){
   assert(pwm[ch*90+45]==(fn?c.fn_color[ch]*peak/255u:caps?c.caps_color[ch]*peak/255u:7));
   assert(pwm[ch*90+86]==(fn?c.fn_color[ch]*peak/255u:7));
  }
 }
 c.indicator_mask=0;memset(pwm,7,sizeof(pwm));f75_custom_indicators(&c,true,true,100,pwm);for(unsigned i=0;i<270;++i)assert(pwm[i]==7);
 puts("Header link/charge states, both themes, quiet mode, menu priority; Caps/Fn priority, exact RGB keys, brightness and v1/v3 records passed.");
}
