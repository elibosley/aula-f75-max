// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
#include "f75_bundle.h"
#include "f75_route.h"
#define F75_ROUTE_BASE 0x3e800u
#define F75_SETTINGS_A 0x38000u
#define F75_SETTINGS_B 0x39000u
#define F75_LEGACY_A 0x3f000u
#define F75_LEGACY_B 0x3f400u
bool f75_settings_load(f75_config *config,f75_custom *custom);
bool f75_settings_save(const f75_config *config,const f75_custom *custom);
void f75_settings_read(uint8_t slot,uint16_t offset,uint8_t out[20]);
void f75_settings_legacy_read(uint8_t slot,uint8_t chunk,uint8_t out[20]);
void f75_settings_diagnostics(uint32_t out[6]);
void f75_settings_debug(uint32_t out[6]);
uint8_t f75_settings_last_bt(uint8_t saved_slot);
bool f75_settings_remember_bt(uint8_t slot);
