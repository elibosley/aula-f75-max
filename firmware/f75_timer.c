#include "f75_timer.h"
static uint32_t duration(uint8_t phase){return phase==F75_FOCUS_WORK?25u*60000u:phase==F75_FOCUS_BREAK?5u*60000u:15u*60000u;}
void f75_timer_init(f75_timer *t,uint32_t now){t->phase=F75_FOCUS_WORK;t->completed=0;t->running=t->alert=false;t->remaining_ms=duration(t->phase);t->last_tick=now;t->finished_at=0;}
void f75_timer_tick(f75_timer *t,uint32_t now){
    if(!t->running)return;
    uint32_t elapsed=now-t->last_tick;t->last_tick=now;
    if(elapsed<t->remaining_ms){t->remaining_ms-=elapsed;return;}
    t->finished_at=now-(elapsed-t->remaining_ms);t->remaining_ms=0;t->running=false;t->alert=true;
    if(t->phase==F75_FOCUS_WORK)t->completed=(uint8_t)(t->completed%4+1);
}
void f75_timer_next(f75_timer *t,uint32_t now){
    f75_timer_tick(t,now);
    if(t->phase==F75_FOCUS_LONG_BREAK)t->completed=0;
    t->phase=t->phase==F75_FOCUS_WORK?(t->completed==4?F75_FOCUS_LONG_BREAK:F75_FOCUS_BREAK):F75_FOCUS_WORK;
    t->remaining_ms=duration(t->phase);t->running=t->alert=false;t->last_tick=now;
}
void f75_timer_toggle(f75_timer *t,uint32_t now){
    f75_timer_tick(t,now);if(!t->remaining_ms)f75_timer_next(t,now);
    t->running=!t->running;t->alert=false;t->last_tick=now;
}
bool f75_timer_pulse(const f75_timer *t,uint32_t now,bool quiet){return t->alert&&!quiet&&(uint32_t)(now-t->finished_at)<4000&&((uint32_t)(now-t->finished_at)/1000)%2==0;}
f75_budget f75_timer_budget(const f75_timer *t,f75_budget b){if(t->running&&b.stage==F75_SLEEP)b.stage=F75_OFF;return b;}
