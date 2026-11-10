#include "f75_navigation.h"
static uint8_t clamp(int value){return (uint8_t)(value<0?0:value>100?100:value);}
static bool modal(const f75_state *s){return s->pairing==F75_PAIR_CONFIRM||s->pairing==F75_PAIR_WAIT;}
static int row_count(const f75_navigation *n){return n->page==F75_FOCUS?3:n->page==F75_MENU||n->page==F75_DEVICES||n->page==F75_KEYS||n->page==F75_LIGHTING?5:4;}
void f75_navigation_init(f75_navigation *n){n->page=F75_HOME;n->cursor=0;n->volume=42;n->editing=0;n->wheel_divisor=1;n->edit_streak=0;n->wheel_pending=0;n->last_direction=0;n->last_turn=0;}
void f75_open_page(f75_navigation *n,f75_page page){if((unsigned)page<=F75_FOCUS){n->page=(uint8_t)page;n->cursor=0;n->editing=0;n->edit_streak=0;n->wheel_pending=0;n->last_turn=0;}}
f75_ui_action f75_turn(f75_state *s,f75_navigation *n,int direction,uint32_t now){
    f75_activity(s,now);if(modal(s)||!direction)return F75_UI_NONE;direction=direction<0?-1:1;
    if(n->editing){
        uint32_t elapsed=now-n->last_turn;
        n->edit_streak=(uint8_t)(n->last_turn&&elapsed<90&&n->last_direction==direction?(n->edit_streak<3?n->edit_streak+1:3):0);
        n->last_direction=(int8_t)direction;
        int step=n->edit_streak>=3?3:1;n->last_turn=now;
        if(n->cursor==1)s->config.brightness=clamp(s->config.brightness+direction*step);
        if(n->cursor==2)s->config.speed=clamp(s->config.speed+direction*step);
        return F75_UI_NONE;
    }
    if(n->page==F75_HOME){if(s->config.wheel==0)n->volume=clamp(n->volume+direction*2);if(s->config.wheel==2)s->config.brightness=clamp(s->config.brightness+direction*2);return F75_UI_HOST_ACTION;}
    if((uint32_t)(now-n->last_turn)>250||n->wheel_pending*direction<0)n->wheel_pending=0;
    n->last_turn=now;n->wheel_pending=(int8_t)(n->wheel_pending+direction);
    int divisor=n->wheel_divisor>=1&&n->wheel_divisor<=3?n->wheel_divisor:1;
    if(n->wheel_pending<divisor&&n->wheel_pending> -divisor)return F75_UI_NONE;
    n->wheel_pending=0;
    int rows=row_count(n);n->cursor=(uint8_t)((n->cursor+direction+rows)%rows);return F75_UI_NONE;
}
f75_ui_action f75_press(f75_state *s,f75_navigation *n,uint32_t now){
    f75_activity(s,now);if(modal(s))return F75_UI_NONE;
    if(s->pairing==F75_PAIR_TIMEOUT){f75_pair_request(s,s->pair_slot,now);return F75_UI_NONE;}
    if(n->editing){n->editing=0;n->last_turn=0;n->edit_streak=0;return F75_UI_NONE;}
    n->wheel_pending=0;
    if(n->page==F75_HOME){f75_open_page(n,F75_MENU);return F75_UI_NONE;}
    if(n->page==F75_MENU){f75_open_page(n,(f75_page)(n->cursor+F75_DEVICES));return F75_UI_NONE;}
    if(n->page==F75_DEVICES){return f75_switch_host(s,n->cursor,now)?F75_UI_CONNECT:F75_UI_NONE;}
    if(n->page==F75_FOCUS)return (f75_ui_action)(F75_UI_TIMER_TOGGLE+n->cursor);
    if(n->cursor==((n->page==F75_KEYS||n->page==F75_LIGHTING)?4:3))return F75_UI_SAVE;
    if(n->page==F75_KEYS){
        if(n->cursor==0){
            uint8_t slot=s->config.active_host;
            if(s->config.os_auto_mask&(1u<<slot))f75_set_os(s,F75_MAC);
            else if(s->config.os[slot]==F75_MAC)f75_set_os(s,F75_WINDOWS);
            else if(s->config.os[slot]==F75_WINDOWS)f75_set_os(s,F75_ANDROID);
            else s->config.os_auto_mask|=1u<<slot;
        }
        if(n->cursor==1)f75_set_caps_swap(s,!s->config.caps_swap);
        if(n->cursor==2)s->config.wheel=(uint8_t)((s->config.wheel+1)%3);
        if(n->cursor==3)s->config.light_mode=(uint8_t)!s->config.light_mode;
    }
    if(n->page==F75_LIGHTING){
        if(n->cursor==0)s->config.effect=(uint8_t)((s->config.effect+1)%5);
        if(n->cursor==3)f75_cycle_color(&s->config);
        if(n->cursor==1||n->cursor==2){n->editing=1;n->last_turn=0;n->edit_streak=0;}
    }
    if(n->page==F75_POWER)s->config.power=n->cursor;
    return F75_UI_NONE;
}
void f75_back(f75_state *s,f75_navigation *n,uint32_t now){f75_activity(s,now);if(s->pairing!=F75_PAIR_IDLE){f75_pair_cancel(s);return;}if(n->editing){n->editing=0;n->last_turn=0;return;}if(n->page!=F75_HOME)f75_open_page(n,n->page==F75_MENU?F75_HOME:F75_MENU);}
f75_ui_action f75_control_key(f75_state *s,f75_navigation *n,uint16_t usage,uint32_t now){
    if(!s->control_layer)return F75_UI_NONE;
    f75_activity(s,now);
    if(usage>=0x1e&&usage<=0x22){f75_open_page(n,(f75_page)(F75_DEVICES+usage-0x1e));return F75_UI_NONE;}
    int direction=(usage==0x51||usage==0x4f||usage==0x0d)?1:(usage==0x52||usage==0x50||usage==0x0e)?-1:0;
    if(direction){
        if(n->page==F75_HOME||n->editing||modal(s))return f75_turn(s,n,direction,now);
        int rows=row_count(n);n->cursor=(uint8_t)((n->cursor+direction+rows)%rows);n->wheel_pending=0;return F75_UI_NONE;
    }
    if(usage==0x28)return f75_press(s,n,now);
    if(usage==0x29)f75_back(s,n,now);
    if(usage==0x16)return F75_UI_SAVE;
    if(usage==0x10)f75_set_os(s,s->config.os[s->config.active_host]==F75_MAC?F75_WINDOWS:F75_MAC);
    return F75_UI_NONE;
}
