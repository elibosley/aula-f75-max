#ifndef F75_PET_H
#define F75_PET_H
#include "f75_core.h"
typedef enum { F75_PET_IDLE,F75_PET_TYPING,F75_PET_FLOW,F75_PET_ZOOM,F75_PET_SLEEPY } f75_pet_mode;
typedef enum { F75_PET_NO_FX,F75_PET_SPARKLES,F75_PET_HEARTS,F75_PET_CONFETTI,F75_PET_SPEEDLINES } f75_pet_effect;
typedef struct {
    uint32_t bucket_at,last_key,last_effect,effect_started,rng,next_blink,blink_started;
    uint16_t buckets[16],wpm;
    uint8_t bucket,mode,effect,previous_effect;
    bool has_key,blinking;
    uint32_t next_bonus,bonus_started,last_streak;
    uint8_t bonus,previous_bonus;
    bool streak_pending;
} f75_pet;
typedef struct { uint16_t wpm;uint8_t mode,frame,effect,phase;int8_t bob; } f75_pet_frame;
void f75_pet_init(f75_pet *pet,uint32_t now,uint32_t seed);
void f75_pet_tick(f75_pet *pet,uint32_t now);
void f75_pet_tap(f75_pet *pet,uint32_t now);
f75_pet_frame f75_pet_get_frame(const f75_pet *pet,uint32_t now,bool quiet);
#endif
