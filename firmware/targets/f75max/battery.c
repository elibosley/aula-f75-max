// SPDX-License-Identifier: GPL-2.0-or-later
#include QMK_KEYBOARD_H
#include "battery.h"

/* Stock 0x7c34 / 0x13278..0x1356c: read-only gauge at 7-bit address
 * 0x63, A14 clock and A15 data. Stock reads voltage at 2/3 and SOC at 4/5.
 * No gauge configuration, calibration, reset or profile writes are used. */
static uint8_t sample[4],phase,percent;
static bool valid;
static uint32_t next_sample,last_good,voltage,successes,failures;
static void delay(void){wait_us(5);}
static void data(bool high){
    /* MODE is shared with the row ISR's A4..A7 updates. Protect only this
     * register change, never the I2C transaction or its settling delays. */
    bool enabled=(NVIC->ISER[0]&(1u<<CT16B3_IRQn))!=0;
    NVIC_DisableIRQ(CT16B3_IRQn);__DSB();__ISB();
    if(high)gpio_set_pin_input_high(A15);
    else {gpio_write_pin_low(A15);gpio_set_pin_output(A15);}
    if(enabled)NVIC_EnableIRQ(CT16B3_IRQn);
}
static void clock(bool high){gpio_write_pin(A14,high);delay();}
static void start(void){data(true);clock(true);data(false);delay();clock(false);}
static void stop(void){data(false);clock(true);data(true);delay();}
static bool send(uint8_t value){
    for(unsigned i=0;i<8;++i){data((value&0x80)!=0);delay();clock(true);clock(false);value<<=1;}
    data(true);clock(true);bool ack=!gpio_read_pin(A15);clock(false);return ack;
}
static uint8_t receive(void){
    uint8_t value=0;data(true);
    for(unsigned i=0;i<8;++i){clock(true);value=(value<<1)|!!gpio_read_pin(A15);clock(false);}
    /* One-byte read, NACK, then STOP. */
    data(true);clock(true);clock(false);return value;
}
bool f75_battery_read_register(uint8_t reg,uint8_t *value){
    start();bool ok=send(0xc6)&&send(reg);
    if(ok){start();ok=send(0xc7);if(ok)*value=receive();}
    stop();return ok;
}
void f75_battery_task(uint32_t now){
    if(valid&&now-last_good>=30000u)valid=false;
    if(!phase&&(int32_t)(now-next_sample)<0)return;
    if(!f75_battery_read_register(2+phase,&sample[phase])){
        ++failures;phase=0;next_sample=now+5000u;return;
    }
    if(++phase<4)return;
    phase=0;next_sample=now+5000u;
    unsigned raw_voltage=((unsigned)sample[0]<<8)|sample[1];
    unsigned raw_soc=((unsigned)sample[2]<<8)|sample[3];
    unsigned mv=raw_voltage*5u/16u;
    if(mv<2800u||mv>4500u||raw_soc>25600u){++failures;return;}
    /* Preserve the supplier's conversion at 0x7bc2: raw SOC * 100 / 24576. */
    unsigned value=raw_soc*100u/24576u;
    percent=value>100u?100u:value;voltage=mv;last_good=now;valid=true;++successes;
}
bool f75_battery_percent(uint8_t *out){if(valid)*out=percent;return valid;}
void f75_battery_diagnostics(uint32_t out[6]){
    out[0]=valid;out[1]=valid?percent:255u;out[2]=voltage;
    out[3]=successes;out[4]=failures;out[5]=last_good;
}
