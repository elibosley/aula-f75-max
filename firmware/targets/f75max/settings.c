// SPDX-License-Identifier: GPL-2.0-or-later
#include QMK_KEYBOARD_H
#include <string.h>
#include "settings.h"

/* Legacy pages remain untouched so older saved settings can migrate. */
__attribute__((used,section(".f75_settings_reserve")))
const uint8_t f75_settings_reserve[2048]={[0 ... 2047]=0xff};
__attribute__((used,section(".f75_custom_reserve")))
const uint8_t f75_custom_reserve[8192]={[0 ... 8191]=0xff};
static uint32_t generation,saves,failures;
static uint8_t active=255;
static bool loaded;
/* Static buffer keeps a 4 KiB record off the 2 KiB process stack. */
static uint32_t words[F75_ENVELOPE_BYTES/4];
static const uint8_t *page(unsigned slot){return (const uint8_t *)(slot?F75_SETTINGS_B:F75_SETTINGS_A);}
static bool ready(void){
    uint16_t start=SN_CT16B4->TC;unsigned attempts=0;
    while(SN_FLASH->STATUS&1u)if((uint16_t)((uint16_t)SN_CT16B4->TC-start)>1875u||++attempts>200000u)return false;
    return !(SN_FLASH->STATUS&4u);
}
static bool erase_record(unsigned slot){
    if(slot>1)return false;
    for(unsigned offset=0;offset<F75_ENVELOPE_BYTES;offset+=1024){
        SN_FLASH->STATUS&=~4u;
        if(!ready())return false;
        SN_FLASH->CTRL=2;SN_FLASH->ADDR=(uintptr_t)page(slot)+offset;SN_FLASH->CTRL=0x42;
        if(!ready())return false;
        const uint32_t *erased=(const uint32_t *)(page(slot)+offset);
        for(unsigned i=0;i<256;++i)if(erased[i]!=UINT32_MAX)return false;
    }
    return true;
}
static bool program_record(unsigned slot){
    if(slot>1)return false;
    /* CRC resides in the last doubleword, so partial records never validate. */
    for(unsigned i=0;i<F75_ENVELOPE_BYTES/4;i+=2){
        if(!ready())return false;
        SN_FLASH->STATUS&=~4u;SN_FLASH->CTRL=1;
        SN_FLASH->ADDR=(uintptr_t)page(slot)+i*4;
        SN_FLASH->DATA=words[i];SN_FLASH->DATA=words[i+1];SN_FLASH->CTRL=0x41;
        if(!ready())return false;
    }
    SN_FLASH->CTRL=0;return !memcmp(page(slot),words,F75_ENVELOPE_BYTES);
}
bool f75_settings_load(f75_config *config,f75_custom *custom){
    bool valid[2];uint32_t gens[2]={0};
    /* Outputs are scratch until a complete record wins. Decode the winner
     * again after probing both, without another 2.5 KiB scratch object. */
    for(unsigned slot=0;slot<2;++slot)valid[slot]=f75_envelope_decode(page(slot),config,custom,&gens[slot]);
    loaded=valid[0]||valid[1];
    if(loaded){
        active=valid[1]&&(!valid[0]||(gens[1]!=gens[0]&&(uint32_t)(gens[1]-gens[0])<0x80000000u));
        generation=gens[active];return f75_envelope_decode(page(active),config,custom,&generation);
    }
    active=255;generation=0;f75_custom_defaults(custom);
    /* The legacy selector already validates both CRCs and handles wraparound. */
    loaded=f75_record_select((const uint8_t *)F75_LEGACY_A,(const uint8_t *)F75_LEGACY_B,config,&generation);
    return loaded;
}
bool f75_settings_save(const f75_config *config,const f75_custom *custom){
    if(!f75_config_valid(config)||!f75_custom_valid(custom))return false;
    f75_envelope_encode(config,custom,generation+1,(uint8_t *)words);
    if(active<2&&!memcmp(page(active)+16,(uint8_t *)words+16,F75_BUNDLE_BYTES)&&
       *(const uint32_t *)(page(active)+F75_ENVELOPE_BYTES-4)==f75_crc32(page(active),F75_ENVELOPE_BYTES-4))return true;
    unsigned target=active==0?1:0;
    if(!erase_record(target)||!program_record(target)){SN_FLASH->CTRL=0;++failures;return false;}
    active=target;++generation;loaded=true;++saves;return true;
}
void f75_settings_read(uint8_t slot,uint16_t offset,uint8_t out[20]){
    memset(out,0xff,20);
    if(slot<2&&offset<F75_ENVELOPE_BYTES){unsigned n=F75_ENVELOPE_BYTES-offset;if(n>20)n=20;memcpy(out,page(slot)+offset,n);}
}
void f75_settings_legacy_read(uint8_t slot,uint8_t chunk,uint8_t out[20]){
    memset(out,0xff,20);if(slot<2&&chunk<8)memcpy(out,(const uint8_t *)(slot?F75_LEGACY_B:F75_LEGACY_A)+chunk*20,20);
}
void f75_settings_diagnostics(uint32_t out[6]){
    out[0]=loaded;out[1]=generation;out[2]=active;out[3]=saves;out[4]=failures;out[5]=F75_ENVELOPE_BYTES;
}
void f75_settings_debug(uint32_t out[6]){
    out[0]=SN_FLASH->STATUS;out[1]=SN_FLASH->CTRL;out[2]=SN_FLASH->ADDR;
    out[3]=generation;out[4]=saves;out[5]=failures;
}
