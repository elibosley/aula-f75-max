#include "f75_pet.h"
#include <assert.h>
#include <stdio.h>
int main(void){
    f75_pet p;f75_pet_init(&p,0,1);assert(p.mode==F75_PET_IDLE&&p.wpm==0);
    f75_pet_tick(&p,p.next_blink);assert(p.blinking);
    f75_pet_init(&p,0,1);uint8_t previous=0;unsigned effects=0;
    for(unsigned i=0;i<100;i++){
        uint32_t now=i*100;uint32_t old=p.last_effect;f75_pet_tap(&p,now);
        if(p.last_effect!=old){assert(p.effect>=1&&p.effect<=4&&p.effect!=previous);previous=p.effect;effects++;}
    }
    assert(p.mode==F75_PET_ZOOM&&p.wpm>=100&&effects>=3);
    f75_pet_frame animated=f75_pet_get_frame(&p,9900,false);assert(animated.frame>=2&&animated.frame<=4);
    f75_pet_frame quiet=f75_pet_get_frame(&p,9900,true);assert(quiet.frame==0&&!quiet.effect&&!quiet.bob&&quiet.wpm==p.wpm);
    f75_pet_tick(&p,11400);assert(p.mode==F75_PET_IDLE);
    f75_pet_tick(&p,14000);assert(p.wpm==0&&!p.effect);
    f75_pet_tick(&p,18000);assert(p.mode==F75_PET_SLEEPY&&f75_pet_get_frame(&p,18000,false).frame==5);
    f75_pet_tap(&p,18001);assert(p.mode==F75_PET_TYPING&&p.wpm==3);
    f75_pet_init(&p,UINT32_MAX-100,0);f75_pet_tap(&p,UINT32_MAX-100);f75_pet_tick(&p,100);assert(p.wpm==3);
    f75_pet_tick(&p,5000);assert(!p.wpm);
    f75_pet_init(&p,0,2);for(unsigned bin=0;bin<16;bin++)for(unsigned n=0;n<100;n++)f75_pet_tap(&p,bin*250);
    assert(p.wpm==999);for(unsigned i=0;i<16;i++)assert(p.buckets[i]<=64);
    f75_pet_init(&p,20000,2);assert(!p.wpm&&!p.effect&&!p.has_key);
    printf("C pet checks passed. state=%zu bytes; pace, reactions, cooldown, quiet mode, sleep, bounds and timer wrap passed.\n",sizeof(p));
}
