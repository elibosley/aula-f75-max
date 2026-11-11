// SPDX-License-Identifier: GPL-2.0-or-later
#include QMK_KEYBOARD_H
#include <stdio.h>
#include <string.h>
#include "f75_core.h"
#include "f75_navigation.h"
#include "f75_timer.h"
#include "f75_pet.h"
#include "panel.h"
#include "raw_hid.h"
#include "wheel.h"
#include "rgb.h"
#include "radio.h"
#include "battery.h"
#include "settings.h"
#include "f75_transfer.h"
#include "f75_bluetooth.h"
#include "f75_clock.h"
#include "os_detection.h"
#include "power.h"
#include "usb_main.h"
#include "storage_probe.h"

/* USB and supplier radio adapter. Only explicit Save writes reserved records. */
static f75_state state;
static f75_clock clock_state;
f75_custom f75_custom_config;
static f75_custom custom_shadow;
static f75_config config_shadow;
static f75_transfer transfer;
static f75_macro_player macro_player;
static uint8_t key_owners[256],mouse_buttons;
static uint8_t macro_trigger=255;
static bool macro_linked;
static f75_navigation navigation;
static f75_timer focus;
static f75_pet pet;
static f75_motion motion;
static f75_view frame;
static uint16_t tile[128 * F75_PANEL_TILE_ROWS];
static uint32_t tile_signatures[128 / F75_PANEL_TILE_ROWS];
static bool tile_valid[128 / F75_PANEL_TILE_ROWS];
static uint16_t held[MATRIX_ROWS][MATRIX_COLS];
static uint32_t release_epoch, last_frame, button_changed, button_down_at;
static uint32_t selector_changed, notice_until, boot_down_at;
static uint8_t frame_y, button_raw, button_stable, selector_raw, selector_stable;
static bool fn, control_space, panel_ready, frame_pending, usb_override, boot_held;
static bool button_held_action;
static uint16_t display_context=UINT16_MAX;
static int direction = 1;
static const char *notice;
extern uint32_t f75_matrix_scans;
extern volatile uint32_t f75_matrix_activity_epoch;
static uint32_t matrix_activity_seen;
static uint32_t idle_yields;
extern bool f75_matrix_ready;
extern uint32_t f75_max_scan_gap_ticks;
static uint32_t perf_tiles, perf_render_ticks, perf_spi_ticks, perf_max_render, perf_max_spi;
static volatile uint32_t complete_frames;
static uint32_t pending_boot_at;
static bool pending_boot;
static bool pending_save;
static uint8_t usb_detected=255;
static uint8_t os_evidence_mask,host_os_slot,host_os_value;
static uint32_t host_os_transaction,host_os_accepted,host_os_rejected;
static bool pending_host_os;
static f75_budget screen_budget;
static bool screen_dark;
static uint32_t benchmark_at;
static bool benchmark_active;
static bool diagnostic_rgb_off;
static bool diagnostic_rgb_blank;
static uint8_t active_slot, last_bt_slot=1,previous_bt_slot=2;
#ifndef F75_USB_ONLY
static uint8_t bluetooth_report_data;
#endif
static bool radio_switch_pending;
static uint8_t pending_radio_slot;
static uint32_t pending_radio_since;
static void request_host(uint8_t slot,bool physical);
static bool usb_selected(void);
static uint8_t selector(void);
static void radio_report(void){
    uint8_t report[8]={0};unsigned count=0;
    unsigned capacity=active_slot>=1&&active_slot<=3?5:6;
    for(unsigned usage=4;usage<=0xe7;++usage)if(key_owners[usage]){
        if(usage>=0xe0&&usage<=0xe7)report[0]|=1u<<(usage-0xe0);
        else if(usage&&usage<=0xff){if(count<capacity)report[2+count]=usage;++count;}
    }
    if(count>capacity)memset(report+2,1,capacity);
#ifndef F75_USB_ONLY
    // Report 2 byte 1 is Constant padding. Byte 7 is Apple TopCase Fn and
    // must remain zero; it is not a vendor data channel.
    if(capacity==5)report[1]=bluetooth_report_data;
#endif
    f75_radio_keyboard(report);
}
uint8_t f75_custom_layer(void){return state.control_layer?2:fn?1:0;}
static void mouse_report(int8_t wheel){
    if(usb_selected()){report_mouse_t report={0};report.buttons=mouse_buttons;report.v=wheel;host_mouse_send(&report);}
    else f75_radio_mouse(mouse_buttons,wheel);
}
static void send_action(void *context,uint16_t usage,bool down){
    (void)context;
    if(usage>=4&&usage<=0xe7){
        if(down){if(key_owners[usage]<255&&key_owners[usage]++==0&&usb_selected())register_code16(usage);}
        else if(key_owners[usage]&&--key_owners[usage]==0&&usb_selected())unregister_code16(usage);
        if(!usb_selected())radio_report();
    }else if(usage>F75_BIND_CONSUMER&&usage<F75_BIND_CONSUMER+0x1000){
        uint16_t consumer=0;
        for(unsigned r=0;r<MATRIX_ROWS;++r)for(unsigned c=0;c<MATRIX_COLS;++c)
            if(held[r][c]>F75_BIND_CONSUMER&&held[r][c]<F75_BIND_CONSUMER+0x1000)consumer=held[r][c]&0xfff;
        if(usb_selected())host_consumer_send(consumer);else f75_radio_consumer(consumer);
    }else if(usage==F75_BIND_SCROLL_UP||usage==F75_BIND_SCROLL_DOWN){
        if(down)mouse_report(usage==F75_BIND_SCROLL_UP?1:-1);
    }else if(usage>=F75_BIND_MOUSE_LEFT&&usage<=F75_BIND_MOUSE_MIDDLE){
        mouse_buttons=0;
        for(unsigned r=0;r<MATRIX_ROWS;++r)for(unsigned c=0;c<MATRIX_COLS;++c)
            if(held[r][c]>=F75_BIND_MOUSE_LEFT&&held[r][c]<=F75_BIND_MOUSE_MIDDLE)mouse_buttons|=1u<<(held[r][c]-F75_BIND_MOUSE_LEFT);
        mouse_report(0);
    }
}
static bool wheel_pressed(void) { return (matrix_get_row(F75_WHEEL_ROW) & (1u << F75_WHEEL_COL)) != 0; }
static uint32_t tile_signature(void) {
    uint32_t hash=0;
    for (unsigned i=0;i<128*F75_PANEL_TILE_ROWS;++i) {
        hash+=tile[i];hash+=hash<<10;hash^=hash>>6;
    }
    hash+=hash<<3;hash^=hash>>11;hash+=hash<<15;
    return hash;
}
#ifndef F75_USB_ONLY
static virtual_timer_t startup_timer;
extern uint32_t __ram0_end__;
static const char *transfer_info;
static uint32_t transfer_info_until;
static uint8_t transfer_info_progress=255;
static void transfer_note(const char *text,uint8_t progress,uint32_t now){
    transfer_info=text;transfer_info_progress=progress;transfer_info_until=now+20000u;
    f75_activity(&state,now);
}
static uint8_t transfer_percent(unsigned completed){
    return (uint8_t)((completed>F75_BUNDLE_BYTES?F75_BUNDLE_BYTES:completed)*100u/F75_BUNDLE_BYTES);
}
static char host_display_text[21];
static uint32_t host_display_started;
static uint32_t host_display_duration;
static bool host_display_bluetooth;
static f75_bluetooth bluetooth_settings;
static uint32_t bluetooth_reply_at;
static bool bluetooth_probe_clear;
static bool bluetooth_read_reply;
static uint16_t bluetooth_read_offset,bluetooth_read_count;
static uint32_t bluetooth_probe_at;
static struct {
    uint8_t bytes[3 + F75_BT_REQUEST_MAX + 4];
    uint8_t count, bits, previous, value;
    uint32_t last_symbol;
    bool active;
} bluetooth_display;

static bool host_display_ready(void) {
    return panel_ready && usb_selected() && USB_DRIVER.state == USB_ACTIVE;
}

static bool bluetooth_display_ready(void) {
    return panel_ready && selector() == 1 && selector_stable == 1 &&
           active_slot >= 1 && active_slot <= 3 && f75_radio_connected() &&
           !radio_switch_pending && state.pairing == F75_PAIR_IDLE;
}

static void host_display_expire(uint32_t now) {
    bool ready = host_display_bluetooth ? bluetooth_display_ready() : host_display_ready();
    if (!ready || now - host_display_started >= host_display_duration) {
        host_display_duration = 0;
    }
}

static void host_display_set(const uint8_t *text, uint8_t length, uint8_t seconds, uint32_t now, bool bluetooth) {
    memcpy(host_display_text, text, length);
    memset(host_display_text + length, 0, sizeof(host_display_text) - length);
    host_display_started = now;
    host_display_duration = (uint32_t)seconds * 1000u;
    host_display_bluetooth = bluetooth;
}

static void bluetooth_reply_probe(uint8_t challenge) {
    if (f75_radio_busy()) return;
    for (unsigned usage = 0; usage < sizeof(key_owners); ++usage) {
        if (key_owners[usage]) return;
    }
    // A bounded forwarding probe uses only the report's Constant padding.
    // The host must qualify forwarding and absence of key events before use.
    uint8_t report[8] = {0};
    static const uint8_t probes[16]={0x80,0x40,0x20,0x10,8,4,2,1,0x55,0xaa,0xfe,0xff,0x7f,0x81,0x5a,0xa5};
    report[1] = probes[challenge];
    f75_radio_keyboard(report);
    bluetooth_probe_clear=true;bluetooth_probe_at=timer_read32();
}

static void bluetooth_settings_reply(uint32_t now) {
    if (!bluetooth_settings.replying) return;
    // Apply/Save emits its own key releases. Drain those before the start
    // marker, so they cannot be mistaken for bytes of a settings response.
    if (transfer.phase == 3 || pending_save) return;
    if (f75_radio_busy() || now - bluetooth_reply_at < 10u) return;
    // Preserve every key and modifier. Only the Constant byte carries data;
    // the Apple Fn field is never used for replies.
    uint8_t value;
    unsigned acknowledged=bluetooth_settings.symbol_index;
    bool more=f75_bluetooth_reply_next(&bluetooth_settings, &value);
    if(bluetooth_read_reply){
        unsigned bytes=acknowledged>2?(acknowledged-2)*7u/8u:0;
        unsigned payload=bytes>11?bytes-11:0;
        if(payload>bluetooth_read_count)payload=bluetooth_read_count;
        transfer_info_progress=transfer_percent(bluetooth_read_offset+payload);
        if(!more)bluetooth_read_reply=false;
    }
    bluetooth_report_data=more?value:0;
    radio_report(); bluetooth_reply_at = now;
}

static void bluetooth_display_receive(uint8_t led, uint32_t now) {
    uint8_t symbol = led >> 5;
    if (!bluetooth_display_ready() || symbol == 0) {
        bluetooth_display.active = false;
        if (!f75_radio_connected() && host_display_bluetooth) host_display_duration = 0;
        return;
    }
    if (symbol == 7) {
        bluetooth_display.count = 0;
        bluetooth_display.bits = 0;
        bluetooth_display.previous = 7;
        bluetooth_display.value = 0;
        bluetooth_display.last_symbol = now;
        bluetooth_display.active = true;
        return;
    }
    if (!bluetooth_display.active || symbol == bluetooth_display.previous) return;
    if (now - bluetooth_display.last_symbol > 1500u) {
        bluetooth_display.active = false;
        return;
    }
    uint8_t step = bluetooth_display.previous == 7 ? symbol : (symbol + 6 - bluetooth_display.previous) % 6;
    if (step < 1 || step > 4) {
        bluetooth_display.active = false;
        return;
    }
    bluetooth_display.previous = symbol;
    bluetooth_display.last_symbol = now;
    bluetooth_display.value = (bluetooth_display.value << 2) | (step - 1);
    bluetooth_display.bits += 2;
    if (bluetooth_display.bits != 8) return;
    uint8_t *data = bluetooth_display.bytes;
    data[bluetooth_display.count++] = bluetooth_display.value;
    bluetooth_display.bits = 0;
    bluetooth_display.value = 0;
    if (bluetooth_display.count < 3) return;
    uint8_t operation = data[0], seconds = data[1], length = data[2];
    if (!((operation == 1 && seconds >= 1 && seconds <= 60 && length >= 1 && length <= 20) ||
          (operation == 2 && seconds == 0 && length == 0) ||
          (operation == 3 && seconds <= 15 && length == 0) ||
          (operation == 4 && seconds == 1 && length >= 13 && length <= F75_BT_REQUEST_MAX))) {
        bluetooth_display.active = false;
        return;
    }
    if (bluetooth_display.count < 3 + length + 4) return;
    bluetooth_display.active = false;
    uint32_t checksum;
    memcpy(&checksum, data + 3 + length, sizeof(checksum));
    if (f75_crc32(data, 3 + length) != checksum) return;
    for (unsigned i = 0; operation == 1 && i < length; ++i) {
        if (data[3 + i] < 32 || data[3 + i] > 126) return;
    }
    if (operation == 1) host_display_set(data + 3, length, seconds, now, true);
    else if (operation == 3) bluetooth_reply_probe(seconds);
    else if (operation == 4) {
        bool accepted=f75_bluetooth_receive(&bluetooth_settings,&transfer,data+3,length,now,&state.config,&f75_custom_config);
        if(accepted&&!bluetooth_settings.response[5]){
            uint8_t command=data[11];unsigned offset=(unsigned)data[12]|((unsigned)data[13]<<8);
            unsigned count=(unsigned)data[14]|((unsigned)data[15]<<8);
            bluetooth_read_reply=command==2;
            if(command==1)transfer_note("Reading settings",0,now);
            else if(command==2){
                bluetooth_read_offset=offset;bluetooth_read_count=count;
                transfer_note("Sending settings",transfer_percent(offset),now);
            }
            else if(command==3)transfer_note("Receiving changes",254,now);
            else if(command==4)transfer_note(transfer.save?"Saving settings":"Applying changes",254,now);
            else if(command==5){transfer_info_until=now+1800u;}
        }
    }
    else if (host_display_bluetooth) host_display_duration = 0;
}

static void host_display_receive(const uint8_t data[32]) {
    uint32_t now = timer_read32();
    host_display_expire(now);
    uint8_t response[32] = {'F', '7', '5', 'a'};
    memcpy(response + 4, data + 4, 4);
    response[8] = 1;
    response[9] = 1; // Invalid request
    response[10] = host_display_ready();
    uint8_t operation = data[9], seconds = data[10], length = data[11];
    bool valid = data[8] == 1 && operation <= 2;
    if (operation == 1) {
        valid = valid && seconds >= 1 && seconds <= 60 && length >= 1 && length <= 20;
    } else {
        valid = valid && seconds == 0 && length == 0;
    }
    for (unsigned index = 0; valid && index < 20; ++index) {
        uint8_t byte = data[12 + index];
        valid = index < length ? byte >= 32 && byte <= 126 : byte == 0;
    }
    if (valid) {
        response[9] = 0;
        if (operation == 1 && !response[10]) {
            response[9] = 2; // USB is not the active route
        } else if (operation == 1) {
            host_display_set(data + 12, length, seconds, now, false);
        } else if (operation == 2 && !host_display_bluetooth) {
            host_display_duration = 0;
        }
    }
    response[11] = !host_display_bluetooth && host_display_duration != 0;
    raw_hid_send(response, sizeof(response));
}

static void startup_guard(virtual_timer_t *timer, void *context) {
    (void)timer; (void)context;
    /* If display bring-up blocks the main task, the system timer can request
     * the same ROM entry as QMK's bootloader path. Only guard the first frame;
     * a later USB suspend must not unexpectedly send the keyboard into ISP. */
    if (!complete_frames) {
        *(volatile uint32_t *)((uintptr_t)&__ram0_end__ - 4) = 0xdeadbeef;
        NVIC_SystemReset();
    }
}
#endif

/* Explicit commands have distinct report signatures. Diagnostics return
 * counters and device state, without returning typed keys. */
void raw_hid_receive(uint8_t *data, uint8_t length) {
    static const uint8_t boot_magic[8] = {0xaa,0x42,0x89,0x5a,0xff,0x71,0x62,0xcc};
    if (length != 32) return;
#ifndef F75_USB_ONLY
    if (!memcmp(data, "F75y", 4)) {
        host_display_receive(data);
        return;
    }
#endif
    if(!memcmp(data,"F75d",4)){
        uint8_t response[32]={'F','7','5','e'};memcpy(response+4,data+4,4);
        f75_budget budget=f75_board_power_budget(&state,timer_read32());
        uint32_t hardware=((SN_GPIO0->DATA>>16)&1u)|((SN_CT16B0->TMRCTRL&1u)<<1)|
            ((SN_CT16B1->TMRCTRL&1u)<<2)|((SN_CT16B2->TMRCTRL&1u)<<3)|((SN_CT16B3->TMRCTRL&1u)<<4)|((idle_yields&65535u)<<16);
        uint32_t values[6]={budget.stage,budget.rgb,budget.screen,budget.animation_fps,f75_rgb_scan_period(),hardware};
        memcpy(response+8,values,sizeof(values));raw_hid_send(response,sizeof(response));return;
    }
    if(!memcmp(data,"F75l",4)&&!memcmp(data+8,"HOSTOS!!",8)){
        uint8_t response[32]={'F','7','5','q'};uint32_t transaction;
        memcpy(response+4,data+4,4);memcpy(&transaction,data+20,4);
        bool valid=USB_DRIVER.state==USB_ACTIVE&&data[16]>=1&&data[16]<=4&&data[17]<2&&
            data[18]==0&&data[19]==0&&data[16]==active_slot&&transaction==state.transaction&&transaction&&
            state.pairing==F75_PAIR_IDLE&&f75_radio_connected()&&(state.config.os_auto_mask&(1u<<data[16]));
        if(valid&&!pending_host_os){
            host_os_slot=data[16];host_os_value=data[17];host_os_transaction=transaction;
            pending_host_os=true;response[8]=1;
        }else ++host_os_rejected;
        raw_hid_send(response,sizeof(response));return;
    }
    if(!memcmp(data,"F75h",4)&&!memcmp(data+8,"TIMESET!",8)){
        uint8_t response[32]={'F','7','5','i'};uint32_t seconds;
        memcpy(response+4,data+4,4);memcpy(&seconds,data+16,4);
        response[8]=f75_clock_set(&clock_state,seconds,timer_read32());
        memcpy(response+12,&clock_state.seconds,4);
        raw_hid_send(response,sizeof(response));return;
    }
    uint8_t reply[32];
#ifndef F75_USB_ONLY
    if (bluetooth_settings.owns_transfer && !memcmp(data, "F75u", 4)) {
        memset(reply, 0, sizeof(reply)); memcpy(reply, "F75t", 4);
        memcpy(reply + 4, data + 4, 4); reply[12] = 1;
        raw_hid_send(reply, sizeof(reply)); return;
    }
#endif
    if(f75_transfer_receive(&transfer,data,reply,timer_read32(),&state.config,&f75_custom_config)){
        if(!reply[12]){
            uint32_t now=timer_read32();unsigned offset=(unsigned)data[13]|((unsigned)data[14]<<8);
            if(data[12]==4)transfer_note("Reading settings",0,now);
            else if(data[12]==5)transfer_note("Sending settings",transfer_percent(offset+17u),now);
            else if(data[12]==1)transfer_note("Receiving changes",0,now);
            else if(data[12]==2)transfer_note("Receiving changes",transfer_percent(transfer.next),now);
            else if(data[12]==3)transfer_note(transfer.save?"Saving settings":"Applying changes",254,now);
            else if(data[12]==6)transfer_info_until=now+1800u;
        }
        raw_hid_send(reply,sizeof(reply));return;
    }
    if(!memcmp(data,"F75j",4)&&data[8]<2){
        uint8_t response[32]={'F','7','5','k'};memcpy(response+4,data+4,8);
        uint16_t offset=(uint16_t)data[9]|((uint16_t)data[10]<<8);
        f75_settings_read(data[8],offset,response+12);raw_hid_send(response,sizeof(response));return;
    }
    if(!memcmp(data,"F75f",4)){
        uint8_t response[32]={'F','7','5','g'};uint32_t values[6];
        memcpy(response+4,data+4,4);f75_settings_debug(values);
        memcpy(response+8,values,sizeof(values));raw_hid_send(response,sizeof(response));return;
    }
    if(!memcmp(data,"F75o",4)){
        uint8_t response[32]={'F','7','5','p'};
        memcpy(response+4,data+4,4);response[8]=usb_detected;response[9]=state.config.os_auto_mask;
        response[10]=active_slot;memcpy(response+11,state.config.os,F75_HOSTS);
        response[16]=state.config.caps_swap;response[17]=os_evidence_mask;response[18]=1;
        response[19]=(uint8_t)f75_radio_connected()|((uint8_t)clock_state.valid<<1);
        memcpy(response+20,&state.transaction,4);memcpy(response+24,&host_os_accepted,4);memcpy(response+28,&host_os_rejected,4);
        raw_hid_send(response,sizeof(response));return;
    }
    if(!memcmp(data,"F75r",4)&&data[8]<2&&data[9]<8){
        uint8_t response[32]={'F','7','5','s'};
        memcpy(response+4,data+4,6);f75_settings_legacy_read(data[8],data[9],response+10);
        raw_hid_send(response,sizeof(response));return;
    }
    if(!memcmp(data,"F75n",4)){
        uint8_t response[32]={'F','7','5','m'};uint32_t values[6];
        memcpy(response+4,data+4,4);f75_settings_diagnostics(values);
        memcpy(response+8,values,sizeof(values));raw_hid_send(response,sizeof(response));return;
    }
    if(!memcmp(data,"F75w",4)&&!memcmp(data+8,"SAVECFG!",8)){
        pending_save=true;uint8_t response[32]={'F','7','5','v'};
        memcpy(response+4,data+4,4);raw_hid_send(response,sizeof(response));return;
    }
    if(!memcmp(data,"F75V",4)){
        uint8_t response[32]={'F','7','5','W'};uint32_t values[6];
        memcpy(response+4,data+4,4);f75_battery_diagnostics(values);
        memcpy(response+8,values,sizeof(values));raw_hid_send(response,sizeof(response));return;
    }
    /* Deliberate, fixed diagnostic actions. No settings, memory addresses,
     * radio, flash or boot options are accepted by this protocol. */
    if (!memcmp(data,"F75T",4) && !memcmp(data+8,"F75DIAG!",8)) {
        if (!memcmp(data+16,"RGB0",4)) {
            diagnostic_rgb_off=true;diagnostic_rgb_blank=false;f75_rgb_suspend(true);
        } else if (!memcmp(data+16,"RGB1",4)) {
            diagnostic_rgb_off=false;diagnostic_rgb_blank=false;f75_rgb_suspend(false);
        } else if (!memcmp(data+16,"RGB2",4)) {
            diagnostic_rgb_off=false;diagnostic_rgb_blank=true;
            f75_rgb_suspend(false);f75_rgb_pause();
        } else if (!memcmp(data+16,"LCD0",4)) {
            panel_ready=f75_panel_init();
            memset(tile_valid,0,sizeof(tile_valid));frame_pending=false;last_frame=0;
        } else return;
        uint8_t response[32]={'F','7','5','U'};
        memcpy(response+4,data+4,4);response[8]=diagnostic_rgb_off;response[9]=panel_ready;response[10]=diagnostic_rgb_blank;
        memcpy(response+16,data+16,4);raw_hid_send(response,sizeof(response));return;
    }
    /* A deliberate, five-second visual test. It changes only rendered pixels;
     * host keys, UI settings and the selected page remain under user control. */
    if (!memcmp(data,"F75A",4)&&!memcmp(data+8,"DRAWTEST",8)) {
        benchmark_at=timer_read32();benchmark_active=true;
        raw_hid_send(data,length);return;
    }
    if (!memcmp(data, "F75V", 4)) {
        uint8_t response[32] = {'F','7','5','W'};
        memcpy(response + 4, data + 4, 4);
        uint32_t counters[6];
        f75_panel_performance(counters);
        memcpy(response + 8, counters, sizeof(counters));
        raw_hid_send(response, sizeof(response));
        return;
    }
    if(!memcmp(data,"F75I",4)) {
        uint8_t response[32]={'F','7','5','J'};memcpy(response+4,data+4,4);
        uint32_t counters[6];f75_panel_bus(counters);memcpy(response+8,counters,sizeof(counters));
        raw_hid_send(response,sizeof(response));return;
    }
    if(!memcmp(data,"F75z",4)) {
        uint8_t response[32]={'F','7','5','q'};
        memcpy(response+4,data+4,4);response[9]=data[9];
        uint32_t address;memcpy(&address,data+10,4);memcpy(response+10,data+10,4);
        bool reserved=false;for(unsigned i=14;i<32;++i)reserved|=data[i]!=0;
        response[8]=reserved?1:f75_storage_probe(data[8],address,data[9],response+14);
        raw_hid_send(response,sizeof(response));return;
    }
    if(!memcmp(data,"F75O",4)) {
        uint8_t response[32]={'F','7','5','Z'};memcpy(response+4,data+4,4);
        uint32_t values[6];f75_radio_diagnostics(values);memcpy(response+8,values,sizeof(values));
        raw_hid_send(response,sizeof(response));return;
    }
    if(!memcmp(data,"F75C",4)) {
        uint8_t response[32]={'F','7','5','D'};memcpy(response+4,data+4,4);
        uint32_t control[]={SN_CT16B0->MCTRL,SN_CT16B1->MCTRL,SN_CT16B2->MCTRL,
                            SN_CT16B0->TC,SN_CT16B1->TC,SN_CT16B2->TC};
        memcpy(response+8,control,sizeof(control));raw_hid_send(response,sizeof(response));return;
    }
    if (!memcmp(data,"F75E",4)) {
        uint8_t response[32]={'F','7','5','F'};
        memcpy(response+4,data+4,4);
        response[8]=state.config.effect;response[9]=state.config.brightness;
        response[10]=state.config.speed;response[11]=state.config.reduced_motion;
        uint32_t detail[5];f75_rgb_details(detail);memcpy(response+12,detail,sizeof(detail));
        raw_hid_send(response,sizeof(response));return;
    }
    if (!memcmp(data, "F75R", 4)) {
        uint8_t response[32]={'F','7','5','S'};
        memcpy(response+4,data+4,4);uint32_t counters[6];
        f75_rgb_diagnostics(counters);memcpy(response+8,counters,sizeof(counters));
        raw_hid_send(response,sizeof(response));return;
    }
    if (!memcmp(data, "F75P", 4)) {
        uint8_t response[32] = {'F','7','5','Q'};
        memcpy(response + 4, data + 4, 4);
        uint32_t counters[] = {perf_tiles, perf_render_ticks, perf_spi_ticks, perf_max_render, perf_max_spi, f75_max_scan_gap_ticks};
        memcpy(response + 8, counters, sizeof(counters));
        raw_hid_send(response, sizeof(response));
        return;
    }
    if (!memcmp(data, "F75K", 4)) {
        /* Only positions absent from the supplier's key layout. This checks
         * whether the wheel switch uses a matrix position on this revision,
         * without reporting the state of any normal typing key. */
        static const uint8_t unused[MATRIX_ROWS] = {0,16,0,32,32,32,0,32,32,0,0,0,8,1,1};
        uint8_t response[32] = {'F','7','5','L'};
        memcpy(response + 4, data + 4, 4);
        for (uint8_t row = 0; row < MATRIX_ROWS; ++row) response[8 + row] = matrix_get_row(row) & unused[row];
        response[23] = gpio_read_pin(B17);
        response[24] = wheel_pressed();
        raw_hid_send(response, sizeof(response));
        return;
    }
    if (!memcmp(data,"F75X",4)) {
        uint8_t response[32]={'F','7','5','Y'};memcpy(response+4,data+4,4);
        uint32_t pwm[6];f75_rgb_pwm_snapshot(pwm);memcpy(response+8,pwm,sizeof(pwm));raw_hid_send(response,sizeof(response));return;
    }
    if (!memcmp(data,"F75M",4)) {
        uint8_t response[32]={'F','7','5','N'};memcpy(response+4,data+4,4);
        uint32_t modes[]={SN_GPIO0->MODE,SN_GPIO1->MODE,SN_GPIO2->MODE,SN_GPIO3->MODE,SN_GPIO0->DATA,SN_GPIO2->DATA};
        memcpy(response+8,modes,sizeof(modes));raw_hid_send(response,sizeof(response));return;
    }
    if (!memcmp(data, "F75G", 4)) {
        uint8_t response[32] = {'F','7','5','H'};
        memcpy(response + 4, data + 4, 4);
        uint32_t pins[] = {SN_GPIO0->DATA, SN_GPIO1->DATA, SN_GPIO2->DATA, SN_GPIO3->DATA,
                           SN_GPIO1->MODE, SN_GPIO1->CFG1};
        memcpy(response + 8, pins, sizeof(pins));
        raw_hid_send(response, sizeof(response));
        return;
    }
    if (!memcmp(data, "F75B", 4) && !memcmp(data + 8, boot_magic, 8)) {
        pending_boot = true; pending_boot_at = timer_read32();
        raw_hid_send(data, length);
        return;
    }
    if (memcmp(data, "F75?", 4)) return;
    uint8_t response[32] = {'F','7','5','!'};
    memcpy(response + 4, data + 4, 4);
    uint32_t counters[] = {timer_read32(), f75_matrix_scans, complete_frames, state.release_epoch};
    memcpy(response + 8, counters, sizeof(counters));
    response[24] = (uint8_t)panel_ready | ((uint8_t)usb_selected() << 1) | ((uint8_t)state.control_layer << 2) | ((uint8_t)f75_matrix_ready << 3);
#ifndef F75_USB_ONLY
    response[24] |= 1u << 4;
#endif
    response[25] = navigation.page;
    response[26] = (uint8_t)gpio_read_pin(B17) | ((uint8_t)gpio_read_pin(A10) << 1) | ((uint8_t)gpio_read_pin(B2) << 2);
    response[27] = (uint8_t)gpio_read_pin(A2) | ((uint8_t)gpio_read_pin(A3) << 1);
    response[28] = 1; response[29] = state.config.caps_swap; response[30] = state.config.os[active_slot];
    response[31] = wheel_pressed();
    raw_hid_send(response, sizeof(response));
}

static void countdown(char out[6], uint32_t seconds) {
    if (seconds > 5999) seconds = 5999;
    unsigned minutes = seconds / 60, remainder = seconds % 60;
    out[0] = '0' + minutes / 10; out[1] = '0' + minutes % 10;
    out[2] = ':';
    out[3] = '0' + remainder / 10; out[4] = '0' + remainder % 10;
    out[5] = 0;
}

static uint8_t selector(void) {
    if (!gpio_read_pin(A10)) return 2; // stock RF position
    if (!gpio_read_pin(B2)) return 1;  // stock Bluetooth position
    return 0;
}
static bool usb_selected(void) { return active_slot==0; }
bool process_detected_host_os_user(os_variant_t os){
    if(os==OS_MACOS||os==OS_IOS)usb_detected=F75_MAC;
    else if(os==OS_WINDOWS)usb_detected=F75_WINDOWS;
    else usb_detected=255; /* Linux/Android fingerprints overlap; do not label them Windows. */
    return true;
}
static void release_keys(void) {
    f75_macro_cancel(&macro_player,send_action,NULL);
    macro_trigger=255;
    clear_keyboard();
    memset(held, 0, sizeof(held));
    memset(key_owners,0,sizeof(key_owners));mouse_buttons=0;
    if(active_slot){uint8_t empty[8]={0};f75_radio_keyboard(empty);f75_radio_consumer(0);f75_radio_mouse(0,0);}
    release_epoch = state.release_epoch;
}
static void show_notice(const char *text) { notice = text; notice_until = timer_read32() + 2200; }
static void commit_host(uint8_t slot,bool physical,bool select_radio){
#ifndef F75_USB_ONLY
    if (slot != active_slot || host_display_bluetooth) host_display_duration = 0;
    transfer_info=NULL;
    bluetooth_display.active = false;
    f75_bluetooth_reset(&bluetooth_settings, &transfer);
    bluetooth_report_data=0;
    bluetooth_probe_clear=false;
#endif
    radio_switch_pending=false;
    f75_pair_cancel(&state);release_keys();
    os_evidence_mask&=1u;
    active_slot=slot;if(slot>=1&&slot<=3){if(slot!=last_bt_slot)previous_bt_slot=last_bt_slot;last_bt_slot=slot;}
    f75_switch_host(&state,slot,timer_read32());
    state.connected_slot=slot?UINT8_MAX:0;
    usb_override=!physical;if(select_radio)f75_radio_select(slot);
    show_notice(slot?"Connecting...":"USB selected");
}
static void request_host(uint8_t slot,bool physical){
    if(slot>=F75_HOSTS)return;
    if(radio_switch_pending){radio_switch_pending=false;f75_radio_select(active_slot);}
    /* Never change the active route for an unavailable hotkey request. */
    if(!physical&&slot&&!f75_radio_seen()){
        state.config.active_host=active_slot;
        show_notice("Move switch to BT");return;
    }
    if(!physical&&!slot&&USB_DRIVER.state!=USB_ACTIVE){
        state.config.active_host=active_slot;
        show_notice("Connect USB cable");return;
    }
    if(!physical&&slot&&!active_slot&&USB_DRIVER.state==USB_ACTIVE){
        /* Historical radio presence is not current availability. Keep USB
         * typing until the exact new selector packet is acknowledged. */
        f75_pair_cancel(&state);state.config.active_host=active_slot;state.connected_slot=0;release_keys();
        if(f75_radio_select(slot)){
            pending_radio_slot=slot;pending_radio_since=timer_read32();radio_switch_pending=true;
            show_notice("Checking radio...");
        }else show_notice("Radio unavailable");
        return;
    }
    commit_host(slot,physical,true);
}
static void action(f75_ui_action result, uint32_t now) {
    if (result == F75_UI_CONNECT) {
        request_host(state.config.active_host,false);
    }
    if (result == F75_UI_SAVE) pending_save=true;
    if (result == F75_UI_TIMER_TOGGLE) f75_timer_toggle(&focus, now);
    if (result == F75_UI_TIMER_NEXT) f75_timer_next(&focus, now);
    if (result == F75_UI_TIMER_RESET) f75_timer_init(&focus, now);
    if (result == F75_UI_HOST_ACTION && navigation.page == F75_HOME) {
        if (state.config.wheel == 0) {
            if(usb_selected())tap_code16(direction>0?KC_VOLU:KC_VOLD);
            else {f75_radio_consumer(direction>0?0xe9:0xea);f75_radio_consumer(0);}
        }
        if (state.config.wheel == 1) {
            mouse_report((int8_t)-direction);
        }
    }
    if (release_epoch != state.release_epoch) release_keys();
}

void keyboard_pre_init_user(void) {
    /* Reset recovery owns the boot-time wheel gesture. Repeating it here would
     * defeat an explicit ROM return while the button is still held. */
    /* Measured stock USB-mode outputs. A13 deselects external SPI flash.
     * A14/A15 are the recovered gauge clock/data. B0/B1/B18 retain their
     * stock levels without assigning an unverified electrical purpose. */
    static const pin_t stock_high[]={A13,A14,A15};
    static const pin_t stock_low[]={B0,B1,B18};
    for(unsigned i=0;i<3;++i){gpio_write_pin_high(stock_high[i]);gpio_set_pin_output(stock_high[i]);}
    for(unsigned i=0;i<3;++i){gpio_write_pin_low(stock_low[i]);gpio_set_pin_output(stock_low[i]);}
    gpio_set_pin_input_high(A10);
    gpio_set_pin_input_high(B2);
}

void keyboard_post_init_user(void) {
    uint32_t now = timer_read32();
    f75_config saved;bool restored=f75_settings_load(&saved,&f75_custom_config);
    f75_init(&state, restored?&saved:NULL, now);
    state.config.active_host = 0;
    state.connected_slot = 0;
    f75_navigation_init(&navigation);
    f75_timer_init(&focus, now);
    f75_pet_init(&pet, now, now ^ 0xf750u);
    selector_raw = selector_stable = selector();
    button_raw = button_stable = 1;
    f75_radio_init();
    request_host(selector_stable==1?last_bt_slot:selector_stable==2?4:0,true);
#ifndef F75_USB_ONLY
    chVTObjectInit(&startup_timer);
    chVTSet(&startup_timer, TIME_MS2I(2000), startup_guard, NULL);
    panel_ready = f75_panel_init();
    f75_rgb_init();
    show_notice(active_slot?"Connecting...":"USB / Fn+1: BT1");
#else
    panel_ready = false;
    show_notice("USB-only diagnostic");
#endif
}

bool process_record_user(uint16_t keycode, keyrecord_t *record) {
    uint32_t now = timer_read32();
    uint8_t row = record->event.key.row, col = record->event.key.col;
    if (row >= MATRIX_ROWS || col >= MATRIX_COLS) return false;
    if (!f75_matrix_ready) return false;
    bool down = record->event.pressed;
    if (keycode == QK_USER_0) {
        fn = down;
        if (!down) {
            control_space = false;
            f75_set_control_layer(&state, false);
            boot_held = false;
        }
        return false;
    }
    f75_activity(&state, now);
    /* Release the exact mapping registered on press, even after Fn changes. */
    if (!down) {
        uint16_t usage=held[row][col];held[row][col]=0;
        if(usage>=F75_BIND_MACRO&&usage<F75_BIND_MACRO+F75_CUSTOM_MACROS){if(macro_trigger==row*MATRIX_COLS+col)f75_macro_release(&macro_player);}
        else if(usage)send_action(NULL,usage,false);
        if (keycode == KC_SPACE && control_space) {
            control_space = false;
            f75_set_control_layer(&state, false);
        }
        if (keycode == KC_ESC) boot_held = false;
        return false;
    }
    if (fn && keycode == KC_SPACE) {
        control_space = true;
        f75_set_control_layer(&state, true);
        release_keys();
        return false;
    }
    if(fn&&!control_space&&keycode==KC_ESC&&state.pairing!=F75_PAIR_IDLE){
        f75_pair_cancel(&state);request_host(active_slot,false);return false;
    }
    if (fn && !control_space && keycode == KC_ESC) {
        boot_held = true; boot_down_at = now;
        show_notice("Hold: bootloader");
        return false;
    }
    if (fn && !control_space && keycode >= KC_1 && keycode <= KC_5) {
        request_host(keycode==KC_5?0:keycode==KC_4?4:keycode-KC_1+1,false);
        return false;
    }
    if(fn&&!control_space&&keycode==KC_P){
        if(active_slot>=1&&active_slot<=3){f75_pair_request(&state,active_slot,now);show_notice("Hold wheel to pair");}
        else show_notice("Select BT1 / 2 / 3");
        return false;
    }
    if (fn && !control_space && keycode == KC_M) {
        f75_set_os(&state, state.config.os[state.config.active_host] == F75_MAC ? F75_WINDOWS : F75_MAC);
        action(F75_UI_NONE, now);
        return false;
    }
    if (state.control_layer) { action(f75_control_key(&state, &navigation, keycode, now), now); return false; }
    if (keycode > 0xff || keycode == KC_NO) return false;
    uint16_t custom=f75_custom_binding(&f75_custom_config,row*MATRIX_COLS+col,fn,0);
    uint16_t mapped=custom?custom:f75_map_usage(&state,keycode);
    if(mapped==F75_BIND_DISABLED)return false;
    if(mapped>=F75_BIND_MACRO&&mapped<F75_BIND_MACRO+F75_CUSTOM_MACROS){
        if(!active_slot||f75_radio_connected()){
            f75_macro_start(&macro_player,&f75_custom_config,mapped-F75_BIND_MACRO,(f75_os)state.config.os[active_slot],now,send_action,NULL);
            held[row][col]=mapped;
            macro_trigger=row*MATRIX_COLS+col;
        }
        return false;
    }
    if (mapped) {
        held[row][col] = mapped;
        send_action(NULL,mapped,true);
        if (keycode >= KC_A && keycode <= KC_SLSH) f75_pet_tap(&pet, now);
    }
    return false;
}

bool encoder_update_user(uint8_t index, bool clockwise) {
    if (index) return false;
    uint32_t now = timer_read32();
    direction = clockwise ? 1 : -1;
    action(f75_turn(&state, &navigation, direction, now), now);
    if (navigation.wheel_pending) f75_motion_nudge(&motion, direction, now);
    return false;
}

static void make_frame(uint32_t now) {
    static const char *pages[] = {"Home", "Menu", "Devices", "Keys", "Lighting", "Power", "Focus", "Screen"};
    static const char *menu[] = {"Devices", "Keys", "Lighting", "Power", "Focus", "Screen"};
    static const char *companions[]={"Mochi","Pip","Ren","Lumi"};
    static const char *faces[]={"Orbit","Minimal","Stars","Companion"};
    static const char *wheels[] = {"Volume", "Scroll", "Brightness"};
    static const char *effects[] = {"Still", "Tidal", "Rain", "Trails", "Constellation"};
    static const char *power[] = {"Balanced", "Endurance", "Desk", "Save settings"};
    memset(&frame, 0, sizeof(frame));
    uint8_t page = navigation.page;
    uint8_t menu_start=page==F75_MENU&&navigation.cursor>=5?1:0;
    frame.home = page == F75_HOME;
    frame.face = state.config.face;
    frame.pet_character=state.config.companion;
    frame.light_mode = state.config.light_mode;
    frame.caps_swap = state.config.caps_swap;
    frame.custom_accent=f75_custom_config.screen_custom;
    frame.accent=(uint16_t)(((f75_custom_config.screen_color[0]>>3)<<11)|((f75_custom_config.screen_color[1]>>2)<<5)|(f75_custom_config.screen_color[2]>>3));
    bool quiet=state.config.reduced_motion||!screen_budget.animation_fps;
    frame.motion = !quiet;
    frame.animation_phase = now / 100;
    frame.selected = navigation.cursor-menu_start;
    frame.editing = navigation.editing;
    snprintf(frame.title, sizeof(frame.title), "%s", pages[page]);
    snprintf(frame.status_left, sizeof(frame.status_left), "%s", usb_selected()?"USB":active_slot==4?"RF":active_slot==1?"BT1":active_slot==2?"BT2":"BT3");
    bool linked=usb_selected()?USB_DRIVER.state==USB_ACTIVE:f75_radio_connected();
    uint8_t battery;
    if(f75_battery_percent(&battery))snprintf(frame.status_right,sizeof(frame.status_right),"%u%%",battery);
    else snprintf(frame.status_right,sizeof(frame.status_right),"--%%");
    snprintf(frame.host_label,sizeof(frame.host_label),"%s",state.config.names[active_slot]);
    snprintf(frame.os, sizeof(frame.os), "%s", state.config.os[active_slot]==F75_MAC?"MAC":state.config.os[active_slot]==F75_ANDROID?"AND":"WIN");
    frame.os_source=!(state.config.os_auto_mask&(1u<<active_slot))?2:(os_evidence_mask&(1u<<active_slot))?1:0;
    f75_clock_text(&clock_state,frame.clock);
    for (uint8_t i = 0; i < 5; ++i) {
        unsigned row = i+menu_start;
        char *text = frame.rows[i];
        if (page == F75_MENU && row < 6) snprintf(text, 20, "%s", menu[row]);
        if(page==F75_SCREEN){
            if(row==0)snprintf(text,20,"Pet: %s",companions[state.config.companion]);
            if(row==1)snprintf(text,20,"Theme: %s",state.config.light_mode?"Light":"Dark");
            if(row==2)snprintf(text,20,"Home: %s",faces[state.config.face]);
            if(row==3)snprintf(text,20,"Motion: %s",state.config.reduced_motion?"Quiet":"Lively");
            if(row==4)snprintf(text,20,"Save settings");
        }
        if (page == F75_DEVICES && row < 5){static const char *slots[]={"USB","BT1","BT2","BT3","RF"};snprintf(text,20,"%c%s %.12s",row==active_slot?(linked?'>':'~'):' ',slots[row],state.config.names[row]);}
        if (page == F75_KEYS) {
            if (row == 0) snprintf(text,20,"%s: %s",state.config.os_auto_mask&(1u<<active_slot)?"Auto":"Layout",state.config.os[active_slot]==F75_MAC?"Mac":state.config.os[active_slot]==F75_ANDROID?"Android":"Windows");
            if (row == 1) snprintf(text,20,"Caps: %s",state.config.caps_swap?(state.config.os[active_slot]==F75_MAC?"Command":"Ctrl"):"Normal");
            if (row == 2) snprintf(text, 20, "Wheel: %s", wheels[state.config.wheel]);
            if (row == 3) snprintf(text, 20, "Screen: %s", state.config.light_mode ? "Light" : "Dark");
            if (row == 4) snprintf(text, 20, "Save settings");
        }
        if (page == F75_LIGHTING) {
            if (row == 0) snprintf(text, 20, "Effect: %s", effects[state.config.effect]);
            if (row == 1) snprintf(text, 20, "Brightness %u%%", state.config.brightness);
            if (row == 2) snprintf(text, 20, "Speed %u%%", state.config.speed);
            if (row == 3) snprintf(text, 20, "Color: %s",f75_color_name(&state.config));
            if (row == 4) snprintf(text, 20, "Save settings");
        }
        if (page == F75_POWER && row < 4) snprintf(text, 20, "%s", power[row]);
        if (page == F75_FOCUS && row < 3) {
            const char *items[] = {focus.running ? "Pause" : "Start", "Next session", "Reset cycle"};
            snprintf(text, 20, "%s", items[row]);
        }
    }
    snprintf(frame.footer, sizeof(frame.footer), "%s", frame.home ? "" : navigation.editing ? "TURN / PRESS done" : "Hold wheel: Back");
    bool alert = focus.alert;
    if (page == F75_FOCUS || alert) {
        uint32_t seconds = (focus.remaining_ms + 999) / 1000;
        frame.home = false; frame.timer = true;
        countdown(frame.clock, seconds);
        snprintf(frame.title, sizeof(frame.title), "%s", focus.phase == F75_FOCUS_WORK ? "Focus" : "Break");
        if (alert) snprintf(frame.footer, sizeof(frame.footer), "Session complete");
        frame.alert_pulse = f75_timer_pulse(&focus, now, state.config.reduced_motion);
    }
    f75_pet_frame pf = f75_pet_get_frame(&pet, now, quiet);
    frame.pet_wpm = pf.wpm; frame.pet_mode = pf.mode; frame.pet_frame = pf.frame;
    frame.pet_effect = pf.effect; frame.pet_phase = pf.phase; frame.pet_bob = pf.bob;
#ifndef F75_USB_ONLY
    if (frame.home && state.pairing == F75_PAIR_IDLE && host_display_duration) {
        memcpy(frame.footer, host_display_text, sizeof(frame.footer));
    }
#endif
    if (frame.home && focus.running) {
        uint32_t seconds = (focus.remaining_ms + 999) / 1000;
        snprintf(frame.footer, sizeof(frame.footer), "%s %02lu:%02lu", focus.phase == 0 ? "Focus" : "Break", (unsigned long)(seconds / 60), (unsigned long)(seconds % 60));
    }
    if(frame.home&&!usb_selected()&&!linked&&!focus.running)snprintf(frame.footer,sizeof(frame.footer),"%s",active_slot==4?"Receiver offline":"Offline / Fn+P");
    if(page==F75_DEVICES)snprintf(frame.footer,sizeof(frame.footer),"%s %s",frame.status_left,linked?"connected":state.pairing==F75_PAIR_WAIT?"pairing":"not connected");
    if(state.pairing==F75_PAIR_CONFIRM){
        frame.home=false;frame.timer=false;snprintf(frame.title,sizeof(frame.title),"Pair BT%u?",state.pair_slot);
        memset(frame.rows,0,sizeof(frame.rows));snprintf(frame.rows[0],20,"Replace saved bond");
        snprintf(frame.rows[1],20,"Hold wheel 1.2s");snprintf(frame.rows[2],20,"Fn+Esc: Cancel");
        snprintf(frame.footer,sizeof(frame.footer),"New pairing");
    }else if(state.pairing==F75_PAIR_WAIT){
        frame.home=false;frame.timer=false;snprintf(frame.title,sizeof(frame.title),"Pairing BT%u",state.pair_slot);
        memset(frame.rows,0,sizeof(frame.rows));snprintf(frame.rows[0],20,"Open Bluetooth");
        snprintf(frame.rows[1],20,"on your device");snprintf(frame.footer,sizeof(frame.footer),"Fn+Esc: Cancel");
    }else if(state.pairing==F75_PAIR_TIMEOUT)snprintf(frame.footer,sizeof(frame.footer),"Pairing timed out");
    if (notice && (int32_t)(notice_until - now) > 0) snprintf(frame.footer, sizeof(frame.footer), "%s", notice);
    if(frame.home&&frame.face==3&&!focus.running&&state.pairing==F75_PAIR_IDLE){
        frame.info_progress=255;
        if(transfer_info&&(int32_t)(transfer_info_until-now)>0){
            snprintf(frame.footer,sizeof(frame.footer),"%s",transfer_info);frame.info_progress=transfer_info_progress;
        }
        frame.pet_info=frame.footer[0]!=0;
    }
    f75_motion_update(&motion, (uint16_t)(page|((uint16_t)menu_start<<8)), frame.selected, direction, now, quiet);
    f75_motion_apply(&motion, &frame);
    if (benchmark_active) {
        if (now-benchmark_at>=5000u) benchmark_active=false;
        else {
            frame.home=false;frame.timer=false;frame.motion=true;frame.content_x=0;
            unsigned step=((now-benchmark_at)/16u)%90u;
            frame.highlight_y=(int16_t)(step<=45?step:90-step);
            frame.selected=(uint8_t)((frame.highlight_y+7)/15);
            snprintf(frame.title,sizeof(frame.title),"Timing test");
            static const char *items[]={"Devices","Keys","Lighting","Power"};
            for(unsigned i=0;i<4;i++)snprintf(frame.rows[i],sizeof(frame.rows[i]),"%s",items[i]);
            snprintf(frame.footer,sizeof(frame.footer),"5 second motion test");
        }
    }
}

void housekeeping_task_user(void) {
    uint32_t now = timer_read32();
#ifndef F75_USB_ONLY
    host_display_expire(now);
    f75_bluetooth_tick(&bluetooth_settings, &transfer, now);
    if (!bluetooth_display_ready()) {
        f75_bluetooth_reset(&bluetooth_settings, &transfer); bluetooth_report_data=0;bluetooth_read_reply=false;
    }
#endif
    f75_clock_tick(&clock_state,now);
    uint32_t activity=f75_matrix_activity_epoch;
    if(activity!=matrix_activity_seen){matrix_activity_seen=activity;f75_activity(&state,now);}
    os_evidence_mask&=state.config.os_auto_mask;
    if(active_slot&&!f75_radio_connected())os_evidence_mask&=(uint8_t)~(1u<<active_slot);
    if(pending_host_os){
        pending_host_os=false;
        if(USB_DRIVER.state==USB_ACTIVE&&f75_host_os_hint(&state,host_os_slot,(f75_os)host_os_value,host_os_transaction,f75_radio_connected())){
            os_evidence_mask|=1u<<host_os_slot;++host_os_accepted;
            if(release_epoch!=state.release_epoch)release_keys();
        }else ++host_os_rejected;
    }
    if(transfer.phase==3){
        if(f75_bundle_decode(transfer.bytes,&config_shadow,&custom_shadow)){
            /* Upload never changes the live route or starts a macro. */
            release_keys();config_shadow.active_host=active_slot;
            state.config=config_shadow;f75_custom_config=custom_shadow;
            os_evidence_mask&=1u;
            ++state.release_epoch;release_epoch=state.release_epoch;
            if(usb_detected<2)f75_detect_os(&state,0,(f75_os)usb_detected);
            f75_activity(&state,now);memset(tile_valid,0,sizeof(tile_valid));frame_pending=false;
            transfer.phase=4;if(transfer.save)pending_save=true;else transfer_note("Changes applied",100,now);
        }else{transfer.phase=6;transfer_note("Invalid settings",255,now);}
    }
    if(pending_save){
        pending_save=false;release_keys();f75_rgb_suspend(true);
        bool saved=f75_settings_save(&state.config,&f75_custom_config);
        if(transfer.phase==4&&transfer.save)transfer.phase=saved?5:7;
        if(!diagnostic_rgb_off){f75_rgb_suspend(false);if(diagnostic_rgb_blank)f75_rgb_pause();}
        show_notice(saved?"Settings saved":"Save failed");
        transfer_note(saved?"Settings saved":"Save failed",saved?100:255,now);
    }
    if (pending_boot && now - pending_boot_at >= 50) { pending_boot = false; release_keys(); f75_rgb_suspend(true); bootloader_jump(); }
#ifndef F75_USB_ONLY
    f75_radio_task(now, bluetooth_display_receive);
    if(bluetooth_probe_clear&&now-bluetooth_probe_at>=50u&&!f75_radio_busy()){
        bluetooth_probe_clear=false;radio_report();
    }
    if (!bluetooth_display_ready()) bluetooth_display.active = false;
#else
    f75_radio_task(now, NULL);
#endif
    bool linked=usb_selected()?USB_DRIVER.state==USB_ACTIVE:f75_radio_connected();
    if(macro_linked&&!linked)release_keys();
    macro_linked=linked;
    if(linked&&(!active_slot||!f75_radio_busy()))f75_macro_tick(&macro_player,&f75_custom_config,now,active_slot?10:2,send_action,NULL);
#ifndef F75_USB_ONLY
    bluetooth_settings_reply(now);
#endif
    f75_battery_task(now);
    if(usb_detected<2){f75_detect_os(&state,0,(f75_os)usb_detected);if(release_epoch!=state.release_epoch)release_keys();}
    if(usb_detected<2&&USB_DRIVER.state==USB_ACTIVE&&(state.config.os_auto_mask&1u))os_evidence_mask|=1u;
    else os_evidence_mask&=(uint8_t)~1u;
    if(active_slot&&f75_radio_connected())state.connected_slot=active_slot;
    else if(active_slot)state.connected_slot=UINT8_MAX;
    uint8_t mode = selector();
    if (mode != selector_raw) { selector_raw = mode; selector_changed = now; }
    if (mode != selector_stable && now - selector_changed >= 20) {
        selector_stable=mode;request_host(mode==1?last_bt_slot:mode==2?4:0,true);
    }
    if(radio_switch_pending){
        uint8_t status=f75_radio_selection_status();
        if(status==F75_RADIO_SELECT_ACKED)commit_host(pending_radio_slot,false,false);
        else if(status==F75_RADIO_SELECT_FAILED||now-pending_radio_since>=250u){
            radio_switch_pending=false;f75_radio_select(active_slot);show_notice("Radio unavailable");
        }
    }
    uint8_t button = !wheel_pressed();
    if (button != button_raw) { button_raw = button; button_changed = now; }
    if (button != button_stable && now - button_changed >= 20) {
        button_stable = button;
        if (!button) {
            button_down_at = now;button_held_action=false;f75_activity(&state,now);
            if(fn&&!control_space&&navigation.page==F75_HOME&&state.pairing==F75_PAIR_IDLE){
                button_held_action=true;
                request_host(active_slot>=1&&active_slot<=3?previous_bt_slot:last_bt_slot,false);
            }
        }
        else if(button_held_action||state.pairing==F75_PAIR_CONFIRM||state.pairing==F75_PAIR_WAIT) { }
        else if (now - button_down_at >= 650) f75_back(&state, &navigation, now);
        else action(f75_press(&state, &navigation, now), now);
    }
    /* Trigger once at the hold threshold, without waiting for release.
     * Pair confirmation owns its deliberate 1.2-second gesture instead. */
    if(!button_stable&&!button_held_action&&state.pairing!=F75_PAIR_CONFIRM&&now-button_down_at>=650u){
        button_held_action=true;
        bool was_pairing=state.pairing!=F75_PAIR_IDLE;
        f75_back(&state,&navigation,now);
        if(was_pairing)request_host(active_slot,false);
    }
    if (boot_held && now - boot_down_at >= 1200) { boot_held = false; release_keys(); f75_rgb_suspend(true); bootloader_jump(); }
    if(state.pairing==F75_PAIR_CONFIRM&&!button_stable&&now-button_down_at>=1200u){
        if(f75_pair_confirm(&state,now-button_down_at,now)){button_held_action=true;release_keys();f75_radio_pair();}
    }
    /* A connection event alone does not prove that a new bond was saved. */
    /* The host may finish discovery after our dialog deadline. A real link
     * on that same slot must also clear timeout, or Auto OS stays blocked. */
    if((state.pairing==F75_PAIR_WAIT||state.pairing==F75_PAIR_TIMEOUT)&&
       state.pair_slot==active_slot&&f75_radio_connected())state.pairing=F75_PAIR_IDLE;
    f75_tick(&state, now);
    bool was_alert=focus.alert;
    f75_timer_tick(&focus, now);
    if(focus.alert&&!was_alert)f75_activity(&state,now);
    f75_pet_tick(&pet, now);
    f75_rgb_tick(&state, now);
    screen_budget=f75_board_power_budget(&state,now);
    if(!screen_budget.screen&&!benchmark_active){
        if(panel_ready)f75_panel_backlight(false);
        screen_dark=true;frame_pending=false;
        /* Yield the main thread so ChibiOS can execute its existing WFI idle
         * loop. Keep system, radio, USB and matrix IRQs enabled. */
        ++idle_yields;wait_ms(1);return;
    }
    if (!panel_ready) return;
    if(screen_dark){
        memset(tile_valid,0,sizeof(tile_valid));frame_pending=false;last_frame=now-1000u;
        /* Leave the backlight off until a complete fresh frame is ready. */
        screen_dark=false;
    }
    uint16_t context=navigation.page|((uint16_t)state.pairing<<3)|((uint16_t)state.config.light_mode<<6)|((uint16_t)focus.alert<<7);
    if(context!=display_context){
        /* A new page owns every pixel, including common background strips.
         * Do not leave a partly completed old page or trust its tile cache. */
        display_context=context;memset(tile_valid,0,sizeof(tile_valid));
        frame_pending=false;last_frame=now-250u;
    }
    /* A single tile per task leaves matrix and USB work between display writes.
     * Keep the view fixed for the whole frame, including while typing. */
    if (!frame_pending) {
        unsigned interval=screen_budget.animation_fps?1000u/screen_budget.animation_fps:1000u;
        if(benchmark_active||((navigation.page!=F75_HOME||f75_motion_active(&motion))&&now-state.last_activity<1200u))interval=16u;
        if(state.config.reduced_motion&&interval<250u)interval=250u;
        if (now - last_frame < interval) return;
        make_frame(now); frame_y = 0; frame_pending = true; last_frame = now;
    }
    uint16_t render_start = (uint16_t)SN_CT16B4->TC;
    bool rendered = f75_render_tile(&frame, frame_y, F75_PANEL_TILE_ROWS, tile, 128 * F75_PANEL_TILE_ROWS);
    uint16_t render_elapsed = (uint16_t)((uint16_t)SN_CT16B4->TC - render_start);
    perf_render_ticks += render_elapsed;
    if (render_elapsed > perf_max_render) perf_max_render = render_elapsed;
    uint16_t spi_start = (uint16_t)SN_CT16B4->TC;
    unsigned index=frame_y/F75_PANEL_TILE_ROWS;
    uint32_t signature=rendered?tile_signature():0;
    bool changed=!tile_valid[index]||tile_signatures[index]!=signature;
    bool sent=rendered&&(!changed||f75_panel_tile(frame_y,F75_PANEL_TILE_ROWS,tile));
    uint16_t spi_elapsed = (uint16_t)((uint16_t)SN_CT16B4->TC - spi_start);
    perf_spi_ticks += spi_elapsed;
    if (spi_elapsed > perf_max_spi) perf_max_spi = spi_elapsed;
    ++perf_tiles;
    if (!sent) {
        panel_ready = false;
        return;
    }
    tile_signatures[index]=signature;tile_valid[index]=true;
    frame_y += F75_PANEL_TILE_ROWS;
    if (frame_y == 128) { frame_pending = false; ++complete_frames;f75_panel_backlight(true); }
}

void suspend_power_down_user(void) {
#ifndef F75_USB_ONLY
    if (!host_display_bluetooth) host_display_duration = 0;
#endif
    if (usb_selected()) f75_rgb_suspend(true);
}
void suspend_wakeup_init_user(void) {
    if(!diagnostic_rgb_off){f75_rgb_suspend(false);if(diagnostic_rgb_blank)f75_rgb_pause();}
}
