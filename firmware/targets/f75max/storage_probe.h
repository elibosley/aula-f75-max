// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
#include <stdint.h>
/* Fixed read operations only: 0=JEDEC ID, 1=24-bit flash read. */
uint8_t f75_storage_probe(uint8_t operation, uint32_t address, uint8_t length, uint8_t *out);
