#ifndef F75_NAVIGATION_H
#define F75_NAVIGATION_H
#include "f75_core.h"
typedef enum { F75_HOME,F75_MENU,F75_DEVICES,F75_KEYS,F75_LIGHTING,F75_POWER,F75_FOCUS,F75_SCREEN } f75_page;
typedef struct { uint8_t page,cursor,volume,editing,wheel_divisor,edit_streak; int8_t wheel_pending,last_direction; uint32_t last_turn; } f75_navigation;
typedef enum { F75_UI_NONE,F75_UI_SAVE,F75_UI_CONNECT,F75_UI_HOST_ACTION,F75_UI_TIMER_TOGGLE,F75_UI_TIMER_NEXT,F75_UI_TIMER_RESET } f75_ui_action;
void f75_navigation_init(f75_navigation *nav);
void f75_open_page(f75_navigation *nav,f75_page page);
f75_ui_action f75_turn(f75_state *state,f75_navigation *nav,int direction,uint32_t now);
f75_ui_action f75_press(f75_state *state,f75_navigation *nav,uint32_t now);
void f75_back(f75_state *state,f75_navigation *nav,uint32_t now);
f75_ui_action f75_control_key(f75_state *state,f75_navigation *nav,uint16_t usage,uint32_t now);
#endif
