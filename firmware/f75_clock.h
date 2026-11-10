// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
#include <stdbool.h>
#include <stdint.h>
typedef struct {uint32_t seconds,tick;bool valid;} f75_clock;
bool f75_clock_set(f75_clock *clock,uint32_t seconds,uint32_t now);
void f75_clock_tick(f75_clock *clock,uint32_t now);
void f75_clock_text(const f75_clock *clock,char out[6]);
