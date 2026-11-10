#include "f75_pet.h"
static uint32_t random_next(f75_pet *p){uint32_t x=p->rng;x^=x<<13;x^=x>>17;x^=x<<5;p->rng=x;return x;}
void f75_pet_init(f75_pet *p,uint32_t now,uint32_t seed){
    *p=(f75_pet){0};p->bucket_at=now;p->last_key=now;p->last_effect=now-3000;p->rng=seed?seed:0x75c11b1u;p->next_blink=now+2000+random_next(p)%3000;
}
void f75_pet_tick(f75_pet *p,uint32_t now){
    uint32_t steps=(uint32_t)(now-p->bucket_at)/250;
    if(steps>=16){for(unsigned i=0;i<16;i++)p->buckets[i]=0;p->bucket=(uint8_t)((p->bucket+steps)%16);}
    else for(uint32_t i=0;i<steps;i++){p->bucket=(uint8_t)((p->bucket+1)%16);p->buckets[p->bucket]=0;}
    p->bucket_at+=steps*250;
    unsigned sum=0;for(unsigned i=0;i<16;i++)sum+=p->buckets[i];p->wpm=(uint16_t)(sum*3>999?999:sum*3);
    uint32_t idle=now-p->last_key;
    p->mode=idle>=8000?F75_PET_SLEEPY:!p->has_key||idle>=1400?F75_PET_IDLE:p->wpm>=100?F75_PET_ZOOM:p->wpm>=60?F75_PET_FLOW:F75_PET_TYPING;
    if(p->effect&&(uint32_t)(now-p->effect_started)>=1400)p->effect=F75_PET_NO_FX;
    if(p->blinking&&(uint32_t)(now-p->blink_started)>=160)p->blinking=false;
    if((int32_t)(now-p->next_blink)>=0){p->blinking=true;p->blink_started=now;p->next_blink=now+2400+random_next(p)%3400;}
}
void f75_pet_tap(f75_pet *p,uint32_t now){
    f75_pet_tick(p,now);uint8_t previous_mode=p->mode;p->has_key=true;p->last_key=now;
    if(p->buckets[p->bucket]<64)p->buckets[p->bucket]++;
    f75_pet_tick(p,now);
    bool faster_entry=p->mode>previous_mode&&p->mode>=F75_PET_FLOW&&p->mode<=F75_PET_ZOOM;
    if(p->wpm>=45&&((uint32_t)(now-p->last_effect)>=2600||(faster_entry&&(uint32_t)(now-p->last_effect)>=1400))){
        uint8_t effect=(uint8_t)(1+random_next(p)%4);
        if(effect==p->previous_effect)effect=(uint8_t)(effect%4+1);
        p->effect=p->previous_effect=effect;p->effect_started=p->last_effect=now;
    }
}
f75_pet_frame f75_pet_get_frame(const f75_pet *p,uint32_t now,bool quiet){
    f75_pet_frame f={.wpm=p->wpm,.mode=p->mode};
    if(p->mode==F75_PET_SLEEPY){f.frame=5;return f;}
    if(quiet)return f;
    f.phase=(uint8_t)((now/90)%16);f.effect=p->effect;
    if(p->mode==F75_PET_IDLE){f.frame=p->blinking?1:0;return f;}
    uint32_t beat=now/(p->mode==F75_PET_ZOOM?85:p->mode==F75_PET_FLOW?120:180);
    f.frame=(uint8_t)(2+beat%2);static const int8_t bob[]={0,-1,0,1};f.bob=bob[beat%4];
    if(p->mode==F75_PET_ZOOM&&p->effect&&beat%4==0)f.frame=4;
    return f;
}
