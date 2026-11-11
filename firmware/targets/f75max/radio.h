// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
#include <stdbool.h>
#include <stdint.h>
void f75_radio_init(void);
void f75_radio_task(uint32_t now, void (*receive_led)(uint8_t value, uint32_t now));
bool f75_radio_select(uint8_t slot);
bool f75_radio_pair(void);
enum { F75_RADIO_SELECT_IDLE, F75_RADIO_SELECT_PENDING, F75_RADIO_SELECT_ACKED, F75_RADIO_SELECT_FAILED };
uint8_t f75_radio_selection_status(void);
void f75_radio_keyboard(const uint8_t report[8]);
void f75_radio_consumer(uint16_t usage);
void f75_radio_scroll(int8_t amount);
void f75_radio_mouse(uint8_t buttons,int8_t wheel);
bool f75_radio_seen(void);
bool f75_radio_connected(void);
bool f75_radio_busy(void);
void f75_radio_diagnostics(uint32_t out[6]);
