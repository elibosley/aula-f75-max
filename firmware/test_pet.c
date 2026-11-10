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
    p.next_bonus=20000;f75_pet_tick(&p,18000);assert(p.mode==F75_PET_SLEEPY&&f75_pet_get_frame(&p,18000,false).frame==5);
    f75_pet_tap(&p,18001);assert(p.mode==F75_PET_TYPING&&p.wpm==3);
    f75_pet_init(&p,UINT32_MAX-100,0);f75_pet_tap(&p,UINT32_MAX-100);f75_pet_tick(&p,100);assert(p.wpm==3);
    f75_pet_tick(&p,5000);assert(!p.wpm);
    f75_pet_init(&p,0,2);for(unsigned bin=0;bin<16;bin++)for(unsigned n=0;n<100;n++)f75_pet_tap(&p,bin*250);
    assert(p.wpm==999);for(unsigned i=0;i<16;i++)assert(p.buckets[i]<=64);
    f75_pet_init(&p,20000,2);assert(!p.wpm&&!p.effect&&!p.has_key);
    f75_pet_init(&p,0,75);uint8_t prior_bonus=0,seen_bonus=0;unsigned scenes=0;
    for(uint32_t now=0;now<600000;now+=20){
        uint8_t before=p.bonus;f75_pet_tick(&p,now);
        f75_pet_frame scene=f75_pet_get_frame(&p,now,false);assert(scene.frame<12);
        assert(f75_pet_get_frame(&p,now,true).frame==0);
        if(p.bonus&&!before){assert(p.bonus!=prior_bonus);prior_bonus=p.bonus;seen_bonus|=(uint8_t)(1u<<p.bonus);scenes++;}
    }
    assert(seen_bonus==14&&scenes>10);
    f75_pet_init(&p,0,75);f75_pet_tick(&p,p.next_bonus);assert(p.bonus);
    uint32_t resumed=p.next_bonus+1;f75_pet_tap(&p,resumed);assert(!p.bonus);
    assert(f75_pet_get_frame(&p,resumed,false).frame>=2&&f75_pet_get_frame(&p,resumed,false).frame<=3);
    f75_pet_init(&p,0,75);for(unsigned i=0;i<35;i++)f75_pet_tap(&p,i*80);
    assert(p.mode==F75_PET_ZOOM&&p.streak_pending);
    f75_pet_tick(&p,4120);assert(p.bonus==4&&!p.streak_pending);
    f75_pet_tick(&p,5220);assert(!p.bonus);
    printf("C pet checks passed. state=%zu bytes; pace, reactions, cooldown, quiet mode, sleep, bounds and timer wrap passed.\n",sizeof(p));
}
