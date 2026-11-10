#include "f75_display.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

extern bool f75_reference_render_tile(const f75_view *,uint8_t,uint8_t,uint16_t *,size_t);

int main(void){
    uint16_t reference[128*128],actual[128*8+2];
    const unsigned sizes[]={1,2,4,8};
    for(unsigned n=0;n<188;n++){
        f75_view v={.status_left="USB",.status_right="100%",.title="Mixed case Agyp",
            .rows={"Devices and keys","WWWWWWWWWWWWWWWWWWW","Brightness 100%","Hold wheel: Back"},
            .footer="Press to select",.clock="25:00",.host_label="Wired keyboard",.os="MAC"};
        v.home=n%4<2;v.timer=n%4==2;v.face=(n/4)%4;v.light_mode=n&1;
        v.selected=(n/3)%5;v.motion=true;v.highlight_y=(int16_t)(n%54)-3;
        v.content_x=(int16_t)(n%29)-14;v.editing=n&2;v.alert_pulse=n%11==0;
        v.timer_progress=n;v.caps_swap=n&4;v.animation_phase=n;
        v.pet_frame=(n/2)%6;v.pet_effect=(n/7)%5;v.pet_phase=n*3;
        v.pet_bob=(int8_t)(n%5)-2;v.pet_wpm=n*7;v.pet_mode=n%5;
        if(n>=128){unsigned p=n-128;v.home=true;v.timer=false;v.face=3;v.light_mode=p&1;v.pet_frame=(p/2)%6;v.pet_effect=p/12;}
        for(unsigned y=0;y<128;y+=8)assert(f75_reference_render_tile(&v,y,8,reference+y*128,128*8));
        for(unsigned s=0;s<4;s++)for(unsigned y=0;y<128;y+=sizes[s]){
            actual[0]=0xa55a;actual[128*sizes[s]+1]=0x5aa5;
            assert(f75_render_tile(&v,y,sizes[s],actual+1,128*sizes[s]));
            assert(actual[0]==0xa55a&&actual[128*sizes[s]+1]==0x5aa5);
            if(memcmp(actual+1,reference+y*128,128*sizes[s]*sizeof(uint16_t))){
                fprintf(stderr,"Pixel mismatch: case %u, tile %u, y %u\n",n,sizes[s],y);return 1;
            }
        }
    }
    puts("188 views, four tile heights: every RGB565 pixel matches the reference renderer.");
    return 0;
}
