// SPDX-License-Identifier: GPL-2.0-or-later
#include QMK_KEYBOARD_H
#include "spi_master.h"
#include "panel.h"
#include "panel_init.h"

#define PANEL_CS B8
#define PANEL_DC D14
#define PANEL_RESET A17
#define PANEL_LIGHT A16
static uint32_t timing[6]; /* setup, transfer, stop ticks; bytes, transactions; reserved */
static uint32_t bus[6]; /* bytes, timeouts, overflows, max sampled byte ticks, STAT, RIS */
void f75_panel_performance(uint32_t out[6]) { for (unsigned i=0;i<6;++i) out[i]=timing[i]; }
void f75_panel_bus(uint32_t out[6]) { for(unsigned i=0;i<6;++i)out[i]=bus[i]; }

/* The SN32 divider is HCLK / (2 * CLKDIV + 2): divider 2 gives 8 MHz.
 * Keep commands and pixels in their original 8-bit, MSB-first format. */
static bool begin(void) {
    uint16_t start = (uint16_t)SN_CT16B4->TC;
    /* Own CS exclusively below. QMK otherwise asserts it during spi_start,
     * before the byte guard is active. */
    if (!spi_start(NO_PIN, false, 0, 2)) return false;
    /* This display owns SPI0 for the transaction. Poll FIFO availability and bus-idle status, avoiding a ChibiOS interrupt for every pixel byte.
     * USB and the system timer remain enabled throughout the transfer. */
    SN_SPI0->IE = 0;
    SN_SPI0->IC = 0x0f;
    gpio_write_pin_high(PANEL_CS);
    timing[0] += (uint16_t)((uint16_t)SN_CT16B4->TC - start);
    ++timing[4];
    return true;
}

/* The checkpoint is refreshed at least every 64 bytes. A stuck transfer is
 * bounded by four milliseconds from that checkpoint, without masking IRQs. */
static inline __attribute__((always_inline)) bool panel_byte(uint8_t value,uint16_t checkpoint) {
    /* Physical scan-only tests corrupt the panel even without LED power.
     * Keep shared-matrix switching outside each selected SPI byte. Defer only
     * the row IRQ; USB, radio and the deadline counter remain live. Restore
     * the prior enable state on success and timeout alike. */
    bool scan_enabled=(NVIC->ISER[0]&(1u<<CT16B3_IRQn))!=0;
    NVIC_DisableIRQ(CT16B3_IRQn);
    __DSB();__ISB();
    gpio_write_pin_low(PANEL_CS);
    SN_SPI0->DATA=value;
    while(SN_SPI0->STAT&0x14u) {
        if((uint16_t)((uint16_t)SN_CT16B4->TC-checkpoint)>=750u) {
            ++bus[1];gpio_write_pin_high(PANEL_CS);
            if(scan_enabled)NVIC_EnableIRQ(CT16B3_IRQn);
            return false;
        }
    }
    (void)SN_SPI0->DATA;
    /* Leave overflow latched until the block check. RX timeout is harmless
     * with polling; RX overflow must remain visible across every byte. */
    SN_SPI0->IC=4u;
    gpio_write_pin_high(PANEL_CS);
    if(scan_enabled)NVIC_EnableIRQ(CT16B3_IRQn);
    return true;
}
static void sample_byte(uint16_t start) {
    uint16_t elapsed=(uint16_t)((uint16_t)SN_CT16B4->TC-start);
    if(elapsed>bus[3])bus[3]=elapsed;
}
static bool transferred(uint16_t start,unsigned sent,bool success) {
    bus[4]=SN_SPI0->STAT;bus[5]=SN_SPI0->RIS;bus[0]+=sent;
    timing[1]+=(uint16_t)((uint16_t)SN_CT16B4->TC-start);timing[3]+=sent;
    if(bus[5]&1u){++bus[2];return false;}
    return success;
}

__attribute__((noinline)) bool f75_panel_transfer(const uint8_t *bytes,unsigned length) {
    uint16_t start=(uint16_t)SN_CT16B4->TC,checkpoint=start;
    unsigned sent=0;
    for(;sent<length;++sent) {
        if(sent&&!(sent&63u))checkpoint=(uint16_t)SN_CT16B4->TC;
        if(!panel_byte(bytes[sent],checkpoint))return transferred(start,sent,false);
        if(!sent)sample_byte(start);
    }
    return transferred(start,sent,true);
}

__attribute__((noinline)) bool f75_panel_pixels(const uint16_t *pixels,unsigned count) {
    uint16_t start=(uint16_t)SN_CT16B4->TC,checkpoint=start;
    unsigned sent=0;
    for(unsigned i=0;i<count;++i) {
        if(i&&!(i&31u))checkpoint=(uint16_t)SN_CT16B4->TC;
        uint16_t pixel=pixels[i];
        if(!panel_byte(pixel>>8,checkpoint))return transferred(start,sent,false);
        ++sent;if(!i)sample_byte(start);
        if(!panel_byte(pixel&255u,checkpoint))return transferred(start,sent,false);
        ++sent;
    }
    return transferred(start,sent,true);
}

static bool finish(bool success) {
    uint16_t start = (uint16_t)SN_CT16B4->TC;
    if (!success) SN_SPI0->CTRL0 |= 0xc0u;
    SN_SPI0->IC = 0x0f;
    spi_stop();
    timing[2] += (uint16_t)((uint16_t)SN_CT16B4->TC - start);
    return success;
}

static bool command(uint8_t value) {
    gpio_write_pin_low(PANEL_DC);
    bool sent = f75_panel_transfer(&value, 1);
    gpio_write_pin_high(PANEL_DC);
    return sent;
}
void f75_panel_backlight(bool enabled) { gpio_write_pin(PANEL_LIGHT, enabled); }

bool f75_panel_init(void) {
    gpio_write_pin_high(PANEL_CS);
    gpio_set_pin_output(PANEL_CS);
    gpio_set_pin_output(PANEL_DC);
    gpio_write_pin_low(PANEL_LIGHT);
    gpio_set_pin_output(PANEL_LIGHT);
    gpio_write_pin_high(PANEL_RESET);
    gpio_set_pin_output(PANEL_RESET);
    /* Retain other peripheral assignments; only SPI0's pin fields change. */
    SN_PFPA->SPI = (SN_PFPA->SPI & ~0xffu) | 0xbfu;
    spi_init();
    /* Match stock: stable high 20ms, reset low 20ms, settle high 150ms. */
    wait_ms(20);
    gpio_write_pin_low(PANEL_RESET);
    wait_ms(20);
    gpio_write_pin_high(PANEL_RESET);
    wait_ms(150);
    if (!begin()) return false;
    for (unsigned i = 0; i < sizeof(f75_panel_commands) / sizeof(f75_panel_commands[0]); ++i) {
        const f75_panel_command *entry = &f75_panel_commands[i];
        if (!command(entry->command) ||
            (entry->length && !f75_panel_transfer(entry->data, entry->length))) return finish(false);
        if (entry->command == 0x11) wait_ms(200);
    }
    finish(true);
    f75_panel_backlight(true);
    return true;
}

bool f75_panel_tile(uint8_t y, uint8_t rows, const uint16_t *pixels) {
    if (!rows || rows > F75_TILE_ROWS || y > 128 - rows || !pixels || !begin()) return false;
    const uint8_t columns[] = {0, 2, 0, 129};
    const uint8_t lines[] = {0, (uint8_t)(y + 1), 0, (uint8_t)(y + rows)};
    if (!command(0x2a) || !f75_panel_transfer(columns, sizeof(columns)) ||
        !command(0x2b) || !f75_panel_transfer(lines, sizeof(lines)) ||
        !command(0x2c)) return finish(false);
    return finish(f75_panel_pixels(pixels, 128u * rows));
}
