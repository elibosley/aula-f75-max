// SPDX-License-Identifier: GPL-2.0-or-later
#include QMK_KEYBOARD_H
#include <string.h>
#include "rgb.h"
#include "f75_lighting.h"
#include "matrix_shared.h"
#include "power.h"
#include "f75_custom.h"
extern f75_custom f75_custom_config;
extern uint8_t f75_custom_layer(void);
extern bool f75_caps_lock_on(void);
extern bool f75_fn_held(void);

/* Supplier-derived, shared key/LED matrix. See scripts/recover_rgb.py.
 * 18 high-active color rows, 15 low-active PWM columns. CT16B0/1/2
 * own the columns; CT16B3 advances rows at the stock 2 MHz / 255 period.
 * The RTOS free counter uses CT16B4, not a lighting timer. */
#define REG(a) (*(volatile uint32_t *)(uintptr_t)(a))
#define KEY 0x5a000000u
static const pin_t rows[18] = {A11,A8,D9,D12,D17,C11,B5,D8,D11,D16,C10,C13,B4,A9,D10,D13,D18,C12};
static const uint32_t masks[4] = {0x0b00u,0x30u,0x3c00u,0x73f00u};
static const uint32_t ports[4] = {0x40044000,0x40046000,0x40048000,0x4004a000};
static const uint32_t columns[15] = {
    0x40002030,0x40002034,0x40002040,0x40004024,0x40004028,
    0x4000402c,0x40002038,0x4000203c,0x40002044,0x40004020,
    0x40000020,0x40002048,0x4000002c,0x40000028,0x40000024};
static void match_write(unsigned column,uint8_t value) {
    /* CT16B1 has unkeyed 16-bit match values. Other PWM banks require KEY. */
    uint32_t address=columns[column];
    REG(address)=(address>=0x40002000u&&address<0x40004000u)?value:KEY|value;
}
static uint8_t duties[2][18][15];
static volatile uint8_t active_buffer, row, active_effect, pending_effect;
static volatile bool pending;
static volatile bool ready, paused, suspended, row_lit;
static volatile bool dark_idle;
static bool frame_initialized;
static uint16_t scan_period=255;
static uint32_t last_update, irq_count, pause_count, frame_count, brightness;

static void rows_off(void) {
    for (unsigned p=0;p<4;++p) REG(ports[p]+0x28)=masks[p];
}
static void timers_stop(void) {
    SN_CT16B0->TMRCTRL=0;SN_CT16B1->TMRCTRL=0;SN_CT16B2->TMRCTRL=0;
}
static void mux(bool on) {
    if(on) {
        /* Exact stock 0x8c00 rearm: enable channel modes before attaching IO.
         * Disconnecting IO alone leaves the previous PWM channel state alive. */
        SN_CT16B0->PWMCTRL=KEY|0x0fu;
        SN_CT16B1->PWMCTRL=0;
        SN_CT16B2->PWMCTRL=KEY|0x0fu;
        SN_CT16B1->PWMIOENB=0x7f0u;
        SN_CT16B0->PWMCTRL=KEY|0x00f0000fu;
        SN_CT16B2->PWMCTRL=KEY|0x00f0000fu;
    } else {
        /* Stock 0x8d42 disables PWM channels as well as their pin mux. */
        SN_CT16B1->PWMIOENB=0;
        SN_CT16B0->PWMCTRL=KEY;
        SN_CT16B2->PWMCTRL=KEY;
    }
}
static void begin_row(void) {
    timers_stop();rows_off();mux(false);
    if(!f75_matrix_sample()) {
        ready=false;paused=true;SN_CT16B3->TMRCTRL=0;
        NVIC_DisableIRQ(CT16B3_IRQn);return;
    }
    for(unsigned c=0;c<15;++c)match_write(c,0);
    if (row==0 && pending) {active_buffer^=1u;active_effect=pending_effect;pending=false;++frame_count;}
    SN_CT16B0->TC=0;SN_CT16B0->PC=0;
    SN_CT16B1->TC=0;SN_CT16B1->PC=0;
    SN_CT16B2->TC=0;SN_CT16B2->PC=0;
    if(!paused&&!dark_idle)mux(true);
    bool lit=false;
    const uint8_t *current=duties[active_buffer][row];
    for(unsigned c=0;c<15;++c) {
        uint8_t duty=current[c];
        match_write(c,duty);lit|=duty!=0;
    }
    row_lit=lit;
    if(lit&&!paused&&!dark_idle)gpio_write_pin_high(rows[row]);
    if(!dark_idle){SN_CT16B0->TMRCTRL=1;SN_CT16B1->TMRCTRL=1;SN_CT16B2->TMRCTRL=1;}
}
/* Keep scanning keys during idle, but stop the unused PWM banks and halve
 * the row-clock frequency. Raw matrix changes wake the main task before
 * debounced host actions, which restores the normal period immediately. */
static void idle_scan(bool idle){
    if(dark_idle==idle)return;
    bool enabled=(NVIC->ISER[0]&(1u<<CT16B3_IRQn))!=0;
    NVIC_DisableIRQ(CT16B3_IRQn);SN_CT16B3->TMRCTRL=0;
    dark_idle=idle;scan_period=idle?511:255;
    rows_off();timers_stop();mux(false);
    SN_CT16B3->MR0=KEY|scan_period;SN_CT16B3->TC=0;SN_CT16B3->PC=0;SN_CT16B3->IC=1;
    NVIC_ClearPendingIRQ(CT16B3_IRQn);
    if(!suspended)SN_CT16B3->TMRCTRL=1;
    if(enabled)NVIC_EnableIRQ(CT16B3_IRQn);
}
OSAL_IRQ_HANDLER(Vector8C) {
    OSAL_IRQ_PROLOGUE();
    SN_CT16B3->TMRCTRL=0;SN_CT16B3->TC=0;SN_CT16B3->PC=0;SN_CT16B3->IC=1;
    if(ready&&!suspended) {uint8_t next=row+1u;row=next==18u?0:next;begin_row();++irq_count;if(ready&&!suspended)SN_CT16B3->TMRCTRL=1;}
    OSAL_IRQ_EPILOGUE();
}
void f75_rgb_pause(void) {
    if(!ready)return;
    NVIC_DisableIRQ(CT16B3_IRQn);
    paused=true;rows_off();mux(false);++pause_count;
    /* The row clock and PWM counters keep running behind the disabled mux.
     * The ISR may update duty registers, but never drives an LED row while
     * the keyboard scanner owns the shared column pins. */
    if(!suspended)NVIC_EnableIRQ(CT16B3_IRQn);
}
void f75_rgb_resume(void) {
    if(!ready||suspended)return;
    NVIC_DisableIRQ(CT16B3_IRQn);
    paused=false;
    if(!dark_idle){mux(true);if(row_lit)gpio_write_pin_high(rows[row]);}
    else {rows_off();timers_stop();mux(false);}
    NVIC_EnableIRQ(CT16B3_IRQn);
}
void f75_rgb_suspend(bool value) {
    if(!ready)return;
    if(value) {
        suspended=true;f75_rgb_pause();
        SN_CT16B3->TMRCTRL=0;timers_stop();
    } else {
        suspended=false;
        SN_CT16B3->IC=1;NVIC_ClearPendingIRQ(CT16B3_IRQn);
        SN_CT16B3->TMRCTRL=1;f75_rgb_resume();
    }
}
void f75_rgb_init(void) {
    rows_off();
    for(unsigned i=0;i<18;++i)gpio_set_pin_output(rows[i]);
    SN_SYS1->AHBCLKEN|=(1u<<5)|(1u<<6)|(1u<<7)|(1u<<8);
    /* PFPA matches supplier exactly. These are the 15 keyboard drive pins;
     * SPI, selector, radio, and encoder pin assignments are preserved. */
    SN_PFPA->CT16B0=0x3302;SN_PFPA->CT16B1=0x700;SN_PFPA->CT16B2=1;
    timers_stop();SN_CT16B3->TMRCTRL=0;
    SN_CT16B0->PRE=23;SN_CT16B1->PRE=23;SN_CT16B2->PRE=23;SN_CT16B3->PRE=23;
    /* If the row ISR stops, hardware stops each PWM counter after 127.5us.
     * All duty thresholds are <=127, so every column has already gone HIGH
     * (off). There is no repeating PWM cycle that can leave one row powered. */
    SN_CT16B0->MR9=KEY|255u;SN_CT16B0->MCTRL=KEY|(1u<<23);
    /* CT16B1 MCTRL is NOT keyed: 0x5a000000 enables MR8/MR9 resets and
     * MR9 interrupt instead of unlocking anything (manual 10.8.10). */
    SN_CT16B1->MR12=255u;SN_CT16B1->MCTRL=0;
    SN_CT16B1->MCTRL2=1u<<8;
    SN_CT16B2->MR9=KEY|255u;SN_CT16B2->MCTRL=KEY|(1u<<23);
    SN_CT16B1->PWMCTRL=0;SN_CT16B1->PWMENB=0x7f0u;
    SN_CT16B3->MR0=KEY|255u;SN_CT16B3->MCTRL=KEY|3u;
    SN_CT16B0->IC=0xffffffff;SN_CT16B1->IC=0xffffffff;
    SN_CT16B2->IC=0xffffffff;SN_CT16B3->IC=0xffffffff;
    ready=true;paused=true;
    NVIC_SetPriority(CT16B3_IRQn,3);
    begin_row();
    SN_CT16B3->TC=0;SN_CT16B3->PC=0;SN_CT16B3->IC=1;
    NVIC_ClearPendingIRQ(CT16B3_IRQn);SN_CT16B3->TMRCTRL=1;
    f75_rgb_resume();
}
/* Integer-only animation, updated outside the IRQ. The IRQ sees a complete
 * buffer at a color-frame boundary; rendering never waits for an animation. */
void f75_rgb_tick(const f75_state *state,uint32_t now) {
    if(!ready)return;
    f75_budget budget=f75_board_power_budget(state,now);
    idle_scan(budget.stage>=F75_OFF);
    if(pending||(uint32_t)(now-last_update)<25u)return;
    if(frame_initialized&&!budget.rgb&&!brightness&&pending_effect==state->config.effect)return;
    last_update=now;
    brightness=budget.rgb;
    uint8_t next=active_buffer^1u;
    if(brightness){
        f75_lighting_frame(&state->config,(uint8_t)brightness,now,&duties[next][0][0]);
        f75_custom_lighting(&f75_custom_config,f75_custom_layer(),(uint8_t)brightness,&duties[next][0][0]);
        f75_custom_indicators(&f75_custom_config,f75_caps_lock_on(),f75_fn_held(),(uint8_t)brightness,&duties[next][0][0]);
    }else memset(duties[next],0,sizeof(duties[next]));
    frame_initialized=true;
    pending_effect=state->config.effect;
    pending=true;
}
void f75_rgb_diagnostics(uint32_t out[6]) {
    out[0]=(uint32_t)ready|((uint32_t)paused<<1)|((uint32_t)suspended<<2);
    out[1]=irq_count;out[2]=pause_count;out[3]=frame_count;out[4]=brightness;out[5]=row;
}

void f75_rgb_details(uint32_t out[5]) {
    uint8_t buffer=active_buffer;
    const uint8_t *data=&duties[buffer][0][0];
    uint32_t hash=2166136261u;
    for(unsigned i=0;i<F75_LIGHT_BYTES;++i)hash=(hash^data[i])*16777619u;
    out[0]=active_effect;out[1]=pending_effect;out[2]=hash;out[3]=frame_count;out[4]=buffer;
}

bool f75_rgb_clock_active(void) {return ready&&!suspended;}
uint16_t f75_rgb_scan_period(void){return scan_period;}

void f75_rgb_pwm_snapshot(uint32_t out[6]) {
    bool enabled=(NVIC->ISER[0]&(1u<<CT16B3_IRQn))!=0;
    NVIC_DisableIRQ(CT16B3_IRQn);
    uint8_t current=row;
    out[0]=current;out[1]=duties[active_buffer][current][0];
    out[2]=SN_CT16B1->MR4;out[3]=SN_CT16B2->MR1;
    out[4]=SN_CT16B0->MR0;out[5]=SN_CT16B0->PWMCTRL;
    if(enabled)NVIC_EnableIRQ(CT16B3_IRQn);
}
