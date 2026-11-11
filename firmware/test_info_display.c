#include "f75_display.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

static void render(f75_view *view,uint16_t *out){
    for(unsigned y=0;y<128;y+=8)assert(f75_render_tile(view,y,8,out+y*128,1024));
}
int main(void){
    static uint16_t baseline[16384],sign[16384],row[130];
    uint32_t heads[4]={0};
    const uint8_t progress[]={0,37,100,254,255};
    for(unsigned character=0;character<4;++character)for(unsigned theme=0;theme<2;++theme){
        f75_view view={.home=true,.face=3,.pet_character=character,.light_mode=theme,.selected=255,.status_left="BT2",.status_right="83%",.clock="12:34"};
        render(&view,baseline);
        for(unsigned i=24*128;i<64*128;++i)heads[character]=heads[character]*33u+baseline[i];
        for(unsigned state=0;state<5;++state)for(unsigned quiet=0;quiet<2;++quiet){
            view.pet_info=true;view.info_progress=progress[state];view.motion=!quiet;view.animation_phase=23;
            strcpy(view.footer,state==3?"Saving settings":"Reading settings");render(&view,sign);
            assert(!memcmp(baseline,sign,72*128*sizeof(uint16_t)));
            assert(memcmp(baseline+77*128,sign+77*128,35*128*sizeof(uint16_t)));
            assert(sign[80*128+20]==0xff7c);
            for(unsigned y=0;y<128;++y){
                row[0]=0xa55a;row[129]=0x5aa5;
                assert(f75_render_tile(&view,y,1,row+1,128));
                assert(row[0]==0xa55a&&row[129]==0x5aa5);
                assert(!memcmp(row+1,sign+y*128,128*sizeof(uint16_t)));
            }
        }
        strcpy(view.footer,"ABCDEFGHIJKLMNOPQRST");render(&view,sign);
        view.pet_info=false;view.footer[0]=0;render(&view,sign);
        assert(!memcmp(sign,baseline,sizeof(sign)));
    }
    for(unsigned a=0;a<4;++a)for(unsigned b=a+1;b<4;++b)assert(heads[a]!=heads[b]);
    puts("Four info-sign companions: both themes, quiet/wait states, unchanged heads, clean exit, tile seams and bounds passed.");
    return 0;
}
