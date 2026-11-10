// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
#include "f75_core.h"
void f75_rgb_init(void);
void f75_rgb_pause(void);
void f75_rgb_resume(void);
void f75_rgb_tick(const f75_state *state, uint32_t now);
void f75_rgb_suspend(bool suspended);
void f75_rgb_diagnostics(uint32_t out[6]);

void f75_rgb_details(uint32_t out[5]);

bool f75_rgb_clock_active(void);

void f75_rgb_pwm_snapshot(uint32_t out[6]);
uint16_t f75_rgb_scan_period(void);
