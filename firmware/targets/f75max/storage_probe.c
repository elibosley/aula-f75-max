// SPDX-License-Identifier: GPL-2.0-or-later
#include QMK_KEYBOARD_H
#include "storage_probe.h"

/* Supplier a7d45875: SPI1 init 0x12d28, read prefix 0x672c,
 * A13 CS, A12 SCK, B11 MOSI, B10 MISO; PFPA SPI1 fields 0xf500.
 * The external asset flash is separate from both MCU firmware stores.
 * No host-supplied SPI opcode, program, erase, or write-enable path exists. */
static bool byte(uint8_t tx, uint8_t *rx, uint16_t start) {
    SN_SPI1->DATA=tx;
    unsigned spins=0;
    while(SN_SPI1->STAT&0x14u) {
        if((uint16_t)((uint16_t)SN_CT16B4->TC-start)>=750u || ++spins>=100000u)return false;
    }
    *rx=(uint8_t)SN_SPI1->DATA;
    return true;
}

uint8_t f75_storage_probe(uint8_t operation,uint32_t address,uint8_t length,uint8_t *out) {
    if(!out || !length || length>18 || operation>1 ||
       (operation==0 && (address || length!=3)) ||
       (operation==1 && (address>=0x1000000u || length>0x1000000u-address)))return 1;
    /* SPI1 is unused by the custom UI. Refuse an active owner, and restore
     * all changed state. SPI0 display and UART2 radio are never configured. */
    uint32_t clock=SN_SYS1->AHBCLKEN&(1u<<13),mux=SN_PFPA->SPI&0xff00u;
    SN_SYS1->AHBCLKEN|=1u<<13;
    if(SN_SPI1->CTRL0&1u){
        if(!clock)SN_SYS1->AHBCLKEN&=~(1u<<13);
        return 3;
    }
    uint32_t mode=SN_GPIO0->MODE&(1u<<13),level=SN_GPIO0->DATA&(1u<<13);
    uint32_t ctrl=SN_SPI1->CTRL0,format=SN_SPI1->CTRL1,divider=SN_SPI1->CLKDIV;
    uint32_t interrupts=SN_SPI1->IE,fetch=SN_SPI1->DFDLY;
    bool scan=(NVIC->ISER[0]&(1u<<CT16B3_IRQn))!=0;
    NVIC_DisableIRQ(CT16B3_IRQn);__DSB();__ISB();
    gpio_write_pin_high(A13);gpio_set_pin_output(A13);
    SN_PFPA->SPI=(SN_PFPA->SPI&~0xff00u)|0xf500u;
    SN_SPI1->CTRL0=0;SN_SPI1->IE=0;SN_SPI1->CTRL1=0;
    SN_SPI1->CLKDIV=11;SN_SPI1->DFDLY=1;SN_SPI1->IC=0x0f;
    SN_SPI1->CTRL0=0x407c1u;
    uint16_t start=(uint16_t)SN_CT16B4->TC;
    uint8_t discard;bool ok;
    gpio_write_pin_low(A13);
    if(operation==0)ok=byte(0x9f,&discard,start);
    else ok=byte(0x03,&discard,start)&&byte(address>>16,&discard,start)&&
            byte(address>>8,&discard,start)&&byte(address,&discard,start);
    for(unsigned i=0;ok&&i<length;++i)ok=byte(0,out+i,start);
    gpio_write_pin_high(A13);
    SN_SPI1->CTRL0=0;SN_SPI1->IC=0x0f;
    SN_SPI1->CTRL1=format;SN_SPI1->CLKDIV=divider;SN_SPI1->DFDLY=fetch;
    SN_SPI1->IE=interrupts;SN_SPI1->CTRL0=ctrl;
    SN_PFPA->SPI=(SN_PFPA->SPI&~0xff00u)|mux;
    SN_SYS1->AHBCLKEN=(SN_SYS1->AHBCLKEN&~(1u<<13))|clock;
    gpio_write_pin(A13,level!=0);
    SN_GPIO0->MODE=(SN_GPIO0->MODE&~(1u<<13))|mode;
    if(scan)NVIC_EnableIRQ(CT16B3_IRQn);
    if(!ok)for(unsigned i=0;i<length;++i)out[i]=0;
    return ok?0:2;
}
