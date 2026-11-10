#include "f75_timer.h"
#include <assert.h>
#include <stdio.h>
int main(void){
    f75_timer t;f75_timer_init(&t,0);assert(t.remaining_ms==1500000&&!t.running);
    f75_timer_toggle(&t,100);f75_timer_tick(&t,1100);assert(t.remaining_ms==1499000);
    f75_timer_toggle(&t,1200);uint32_t paused=t.remaining_ms;
    f75_timer_tick(&t,90000);assert(t.remaining_ms==paused&&!t.running);
    f75_timer_toggle(&t,90000);f75_timer_tick(&t,90000+paused);
    assert(t.alert&&!t.running&&t.remaining_ms==0&&t.completed==1);
    uint32_t end=t.finished_at;
    assert(f75_timer_pulse(&t,end,false)&&!f75_timer_pulse(&t,end,true));
    assert(!f75_timer_pulse(&t,end+1000,false)&&f75_timer_pulse(&t,end+2000,false));
    assert(!f75_timer_pulse(&t,end+4000,false));
    f75_timer_tick(&t,end+100000);assert(t.alert&&t.phase==F75_FOCUS_WORK&&t.completed==1);
    f75_timer_toggle(&t,end+100000);assert(t.phase==F75_FOCUS_BREAK&&t.running&&t.remaining_ms==300000);
    f75_timer_next(&t,end+100100);assert(t.phase==F75_FOCUS_WORK&&!t.running&&t.completed==1);
    f75_timer_next(&t,end+100200);assert(t.completed==1&&t.phase==F75_FOCUS_BREAK);
    f75_timer_init(&t,UINT32_MAX-100);f75_timer_toggle(&t,UINT32_MAX-100);f75_timer_tick(&t,899);
    assert(t.remaining_ms==1499000);
    uint32_t now=0;f75_timer_init(&t,now);
    for(unsigned i=1;i<=4;i++){
        f75_timer_toggle(&t,now);now+=1500000;f75_timer_tick(&t,now);assert(t.completed==i&&t.alert);
        f75_timer_next(&t,now);assert(t.phase==(i==4?F75_FOCUS_LONG_BREAK:F75_FOCUS_BREAK));
        assert(t.remaining_ms==(i==4?900000:300000));f75_timer_next(&t,now);
    }
    f75_timer_toggle(&t,now);f75_budget b={F75_SLEEP,0,0,0};b=f75_timer_budget(&t,b);
    assert(b.stage==F75_OFF&&!b.rgb&&!b.screen&&!b.animation_fps);
    now+=1600000;f75_timer_tick(&t,now);assert(t.completed==1&&t.alert&&!f75_timer_pulse(&t,now,false));
    f75_timer_init(&t,now);assert(!t.alert&&!t.running&&t.completed==0);
    printf("C timer checks passed. timer=%zu bytes; wrap, pause, late tick, long break, pulse and power checks passed.\n",sizeof(t));
}
