#include "f75_pet.h"
static uint32_t random_next(f75_pet *p){uint32_t x=p->rng;x^=x<<13;x^=x>>17;x^=x<<5;p->rng=x;return x;}
void f75_pet_init(f75_pet *p,uint32_t now,uint32_t seed){
    *p=(f75_pet){0};p->bucket_at=now;p->last_key=now;p->last_effect=now-3000;p->rng=seed?seed:0x75c11b1u;p->next_blink=now+2000+random_next(p)%3000;
    p->next_bonus=now+6000+random_next(p)%6001;p->last_streak=now-12000;
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
    static const uint16_t duration[]={0,2300,2100,1740,1100};
    if(p->bonus&&(uint32_t)(now-p->bonus_started)>=duration[p->bonus]){
        p->bonus=0;p->next_bonus=now+12000+random_next(p)%16001;
    }
    if(p->mode>=F75_PET_TYPING&&p->mode<=F75_PET_ZOOM)p->bonus=0;
    else if(p->streak_pending){p->bonus=4;p->bonus_started=now;p->last_streak=now;p->streak_pending=false;}
    else if(!p->bonus&&(int32_t)(now-p->next_bonus)>=0){
        uint8_t bonus=(uint8_t)(1+random_next(p)%3);
        if(bonus==p->previous_bonus)bonus=(uint8_t)(1+(bonus+random_next(p)%2)%3);
        p->bonus=p->previous_bonus=bonus;p->bonus_started=now;
    }
}
void f75_pet_tap(f75_pet *p,uint32_t now){
    f75_pet_tick(p,now);uint8_t previous_mode=p->mode;p->has_key=true;p->last_key=now;
    if(p->buckets[p->bucket]<64)p->buckets[p->bucket]++;
    f75_pet_tick(p,now);
    bool faster_entry=p->mode>previous_mode&&p->mode>=F75_PET_FLOW&&p->mode<=F75_PET_ZOOM;
    p->bonus=0;p->next_bonus=now+5000+random_next(p)%6001;
    if(faster_entry&&(uint32_t)(now-p->last_streak)>=12000)p->streak_pending=true;
    if(p->wpm>=45&&((uint32_t)(now-p->last_effect)>=2600||(faster_entry&&(uint32_t)(now-p->last_effect)>=1400))){
        uint8_t effect=(uint8_t)(1+random_next(p)%4);
        if(effect==p->previous_effect)effect=(uint8_t)(effect%4+1);
        p->effect=p->previous_effect=effect;p->effect_started=p->last_effect=now;
    }
}
f75_pet_frame f75_pet_get_frame(const f75_pet *p,uint32_t now,bool quiet){
    f75_pet_frame f={.wpm=p->wpm,.mode=p->mode};
    if(quiet)return f;
    if(p->bonus){
        f.mode=(uint8_t)(4+p->bonus);
        static const uint8_t frames[4][7]={{6,7,6,0},{8,9,8,0},{10,11,10,11,10,11,0},{4,0,4,0}};
        static const uint16_t durations[4][7]={{350,1300,350,300},{350,1100,350,300},{240,240,240,240,240,240,300},{350,150,350,250}};
        uint32_t elapsed=now-p->bonus_started;unsigned clip=p->bonus-1;
        for(unsigned i=0;i<7&&durations[clip][i];i++){
            if(elapsed<durations[clip][i]){f.frame=frames[clip][i];return f;}
            elapsed-=durations[clip][i];
        }
        return f;
    }
    if(p->mode==F75_PET_SLEEPY){f.frame=5;return f;}
    f.phase=(uint8_t)((now/90)%16);f.effect=p->effect;
    if(p->mode==F75_PET_IDLE){f.frame=p->blinking?1:0;return f;}
    uint32_t beat=now/(p->mode==F75_PET_ZOOM?85:p->mode==F75_PET_FLOW?120:180);
    f.frame=(uint8_t)(2+beat%2);static const int8_t bob[]={0,-1,0,1};f.bob=bob[beat%4];
    return f;
}
