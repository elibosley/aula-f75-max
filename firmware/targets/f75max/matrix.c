// SPDX-License-Identifier: GPL-2.0-or-later
#include QMK_KEYBOARD_H
#include "rgb.h"
#include "matrix_shared.h"

/* Stock scanner: assert one drive high, settle, read six high-active inputs.
 * Do not enable internal pull-ups on these inputs. These sense pins have no
 * pull-down mode. The electrical polarity still needs a physical check. */
static const pin_t drive[MATRIX_ROWS] = MATRIX_ROW_PINS;
static const pin_t sense[MATRIX_COLS] = MATRIX_COL_PINS;
uint32_t f75_matrix_scans;
volatile uint32_t f75_matrix_activity_epoch;
uint32_t f75_max_scan_gap_ticks;
static uint16_t scan_tick;
bool f75_matrix_ready;
static bool clear_seen;
static uint32_t clear_at;
static uint8_t sampled[2][MATRIX_ROWS];
static volatile uint8_t sampled_front;
static uint8_t sample_row, sample_back=1;
static volatile uint32_t sample_epoch;
static uint32_t consumed_epoch;
static uint8_t last_raw[MATRIX_ROWS];
static void record_activity(unsigned row,uint8_t value){
    if(last_raw[row]!=value){last_raw[row]=value;++f75_matrix_activity_epoch;}
}
static void record_scan(void) {
    uint16_t tick=(uint16_t)SN_CT16B4->TC;
    uint16_t elapsed=tick-scan_tick;
    if(f75_matrix_scans&&elapsed>f75_max_scan_gap_ticks)f75_max_scan_gap_ticks=elapsed;
    scan_tick=tick;++f75_matrix_scans;
}
/* Fixed, bounded settle inside the LED-row IRQ. No scheduler calls in IRQ.
 * Three ticks guarantee at least 10.7us even when entered near a tick edge. */
static void drive_mode(bool output) {
    /* Stock 0x3ada/0x3bac: GPIO outputs only during sampling; input while
     * the PWM peripheral owns the same pads. Preserve their CFG fields. */
    if(output){SN_GPIO0->MODE|=0xf0u;SN_GPIO2->MODE|=0x43ffu;}
    else {SN_GPIO0->MODE&=~0xf0u;SN_GPIO2->MODE&=~0x43ffu;}
}
bool f75_matrix_sample(void) {
    drive_mode(true);
    SN_GPIO0->BCLR=0xf0u;SN_GPIO2->BCLR=0x43ffu;
    gpio_write_pin_high(drive[sample_row]);
    uint16_t start=(uint16_t)SN_CT16B4->TC;
    unsigned attempts=0;
    while((uint16_t)((uint16_t)SN_CT16B4->TC-start)<3u) {
        if(++attempts==4096u){gpio_write_pin_low(drive[sample_row]);drive_mode(false);return false;}
    }
    uint8_t value=0;
    for(unsigned col=0;col<MATRIX_COLS;++col)if(gpio_read_pin(sense[col]))value|=1u<<col;
    gpio_write_pin_low(drive[sample_row]);
    drive_mode(false);
    record_activity(sample_row,value);
    sampled[sample_back][sample_row]=value;
    if(++sample_row==MATRIX_ROWS){
        sample_row=0;sampled_front=sample_back;sample_back^=1u;
        record_scan();++sample_epoch;
    }
    return true;
}

void matrix_init_custom(void) {
    for (unsigned i = 0; i < MATRIX_ROWS; ++i) {
        gpio_write_pin_low(drive[i]);
        gpio_set_pin_output(drive[i]);
    }
    for (unsigned i = 0; i < MATRIX_COLS; ++i) {
        gpio_set_pin_input(sense[i]);
    }
}

bool matrix_scan_custom(matrix_row_t current[MATRIX_ROWS]) {
    bool changed=false,pressed=false;
    if(f75_rgb_clock_active()) {
        if(consumed_epoch==sample_epoch)return false;
        /* Copy a complete key frame. This does not touch the LED mux, GPIO,
         * PWM counters or row clock. The IRQ owns all shared-pin transitions. */
        NVIC_DisableIRQ(CT16B3_IRQn);
        uint8_t front=sampled_front;
        for(unsigned row=0;row<MATRIX_ROWS;++row){
            uint8_t value=sampled[front][row];
            changed|=current[row]!=value;pressed|=value!=0;current[row]=value;
        }
        consumed_epoch=sample_epoch;
        NVIC_EnableIRQ(CT16B3_IRQn);
    } else {
        /* USB-only bring-up / USB suspend: no active lighting timer. */
        f75_rgb_pause();drive_mode(true);
        for(unsigned row=0;row<MATRIX_ROWS;++row){
            matrix_row_t value=0;gpio_write_pin_high(drive[row]);wait_us(MATRIX_IO_DELAY);
            for(unsigned col=0;col<MATRIX_COLS;++col)if(gpio_read_pin(sense[col]))value|=(matrix_row_t)1<<col;
            gpio_write_pin_low(drive[row]);changed|=current[row]!=value;pressed|=value!=0;current[row]=value;
            record_activity(row,(uint8_t)value);
        }
        f75_rgb_resume();record_scan();
    }
    /* No host key presses until the whole matrix has been clear for 25 ms.
     * A held startup key or wrong electrical assumption cannot send shortcuts. */
    if (!f75_matrix_ready) {
        uint32_t now = timer_read32();
        if (pressed) clear_seen = false;
        else if (!clear_seen) { clear_seen = true; clear_at = now; }
        else if (now - clear_at >= 25) f75_matrix_ready = true;
    }
    return changed;
}

