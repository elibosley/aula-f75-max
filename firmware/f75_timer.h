#ifndef F75_TIMER_H
#define F75_TIMER_H
#include "f75_core.h"
typedef enum { F75_FOCUS_WORK,F75_FOCUS_BREAK,F75_FOCUS_LONG_BREAK } f75_focus_phase;
typedef struct {
    uint32_t remaining_ms,last_tick,finished_at;
    uint8_t phase,completed;
    bool running,alert;
} f75_timer;
void f75_timer_init(f75_timer *timer,uint32_t now);
void f75_timer_tick(f75_timer *timer,uint32_t now);
void f75_timer_toggle(f75_timer *timer,uint32_t now);
void f75_timer_next(f75_timer *timer,uint32_t now);
bool f75_timer_pulse(const f75_timer *timer,uint32_t now,bool quiet);
f75_budget f75_timer_budget(const f75_timer *timer,f75_budget budget);
#endif
