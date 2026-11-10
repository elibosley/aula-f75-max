// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
#include <stdbool.h>
#include <stdint.h>
void f75_battery_task(uint32_t now);
bool f75_battery_percent(uint8_t *percent);
void f75_battery_diagnostics(uint32_t out[6]);
