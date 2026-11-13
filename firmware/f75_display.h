#ifndef F75_DISPLAY_H
#define F75_DISPLAY_H
#include "f75_core.h"

enum { F75_LINK_UNKNOWN, F75_LINK_OFFLINE, F75_LINK_CONNECTING, F75_LINK_CONNECTED, F75_LINK_PAIRING };
enum { F75_POWER_UNKNOWN, F75_POWER_BATTERY, F75_POWER_EXTERNAL, F75_POWER_CHARGING };

typedef struct {
    char status_left[8],status_right[8],title[20],rows[5][20],footer[21];
    char clock[6],host_label[19],os[4];
    uint8_t selected,animation_phase,face;
    bool home,caps_swap,motion,editing;
    int16_t highlight_y,content_x;
    bool light_mode,timer,alert_pulse;
    uint8_t timer_progress;
    uint16_t pet_wpm;
    uint8_t pet_mode,pet_frame,pet_effect,pet_phase;
    int8_t pet_bob;
    uint8_t os_source; /* 0 saved, 1 detected automatically, 2 manual */
    uint16_t accent;
    bool custom_accent;
    uint8_t pet_character;
    bool pet_info;
    uint8_t info_progress; /* 0..100 acknowledged work, 254 waiting, 255 no bar */
    uint8_t link_state,power_state;
    bool visitor,visitor_flip;
    uint8_t visitor_frame;
    int16_t visitor_x;
} f75_view;

/* Q8 springs. Selection changes synchronously; only its visual position lags.
   Retarget the same spring during a burst instead of queueing animations. */
typedef struct {
    int32_t selection,velocity,slide,slide_velocity;
    uint32_t last_step,last_input;
    uint16_t context;
    uint8_t selected,flags;
} f75_motion;
void f75_motion_update(f75_motion *motion,uint16_t context,uint8_t selected,int direction,uint32_t now,bool quiet);
void f75_motion_nudge(f75_motion *motion,int direction,uint32_t now);
bool f75_motion_active(const f75_motion *motion);
void f75_motion_apply(const f75_motion *motion,f75_view *view);

/* RGB565 tile output: no full-screen framebuffer and no dynamic allocation.
   The SPI adapter supplies each tile in order. It owns panel offsets and byte order. */
bool f75_render_tile(const f75_view *view,uint8_t y,uint8_t rows,uint16_t *pixels,size_t capacity);
/* Conservative eight-row dirty mask for menus and companion Home frames.
 * Appearance changes and unclassified pages require a complete repaint. */
uint16_t f75_changed_tiles(const f75_view *previous,const f75_view *next);
#endif
