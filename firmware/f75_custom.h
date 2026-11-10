// SPDX-License-Identifier: GPL-2.0-or-later
#ifndef F75_CUSTOM_H
#define F75_CUSTOM_H
#include "f75_core.h"
enum {F75_CUSTOM_KEYS=90,F75_CUSTOM_LAYERS=3,F75_CUSTOM_MACROS=8,F75_MACRO_STEPS=32,F75_CUSTOM_BYTES=3072};
enum {F75_BIND_INHERIT=0,F75_BIND_DISABLED=0xffff,F75_BIND_MACRO=0x8000,F75_BIND_CONSUMER=0x4000,
      F75_BIND_SCROLL_UP=0x2001,F75_BIND_SCROLL_DOWN=0x2002,F75_BIND_MOUSE_LEFT=0x2011,
      F75_BIND_MOUSE_RIGHT=0x2012,F75_BIND_MOUSE_MIDDLE=0x2013,F75_MACRO_PRIMARY=0x100,F75_MACRO_UP=0x8000};
typedef struct {uint16_t usage,delay_ms;} f75_macro_step;
typedef struct {
    uint16_t keys[2][F75_CUSTOM_KEYS];
    uint8_t colors[F75_CUSTOM_LAYERS][F75_CUSTOM_KEYS][3];
    uint8_t colored[F75_CUSTOM_LAYERS][F75_CUSTOM_KEYS];
    uint8_t layer_colors[F75_CUSTOM_LAYERS][3],layer_mask;
    uint8_t macro_length[F75_CUSTOM_MACROS],macro_repeat[F75_CUSTOM_MACROS];
    f75_macro_step steps[F75_CUSTOM_MACROS][F75_MACRO_STEPS];
    uint8_t screen_color[3],screen_custom;
} f75_custom;
typedef struct {
    uint32_t due;
    uint8_t held[32],slot,step,os;
    bool active,repeat;
} f75_macro_player;
typedef void (*f75_macro_emit)(void *context,uint16_t usage,bool down);
void f75_custom_defaults(f75_custom *custom);
bool f75_custom_valid(const f75_custom *custom);
void f75_custom_encode(const f75_custom *custom,uint8_t bytes[F75_CUSTOM_BYTES]);
bool f75_custom_decode(const uint8_t bytes[F75_CUSTOM_BYTES],f75_custom *custom);
uint16_t f75_custom_binding(const f75_custom *custom,uint8_t key,bool function,uint16_t stock);
void f75_custom_lighting(const f75_custom *custom,uint8_t layer,uint8_t brightness,uint8_t pwm[270]);
bool f75_macro_start(f75_macro_player *player,const f75_custom *custom,uint8_t slot,f75_os os,uint32_t now,f75_macro_emit emit,void *context);
void f75_macro_tick(f75_macro_player *player,const f75_custom *custom,uint32_t now,uint16_t gap_ms,f75_macro_emit emit,void *context);
void f75_macro_cancel(f75_macro_player *player,f75_macro_emit emit,void *context);
void f75_macro_release(f75_macro_player *player);
#endif
