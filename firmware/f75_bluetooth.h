// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
#include "f75_transfer.h"
#include "f75_clock.h"

enum { F75_BT_REQUEST_MAX = 64, F75_BT_READ_MAX = 256, F75_BT_PATCH_MAX = 48,
       F75_BT_RESPONSE_MAX = 11 + F75_BT_READ_MAX + 4 };
typedef struct {
    uint8_t response[F75_BT_RESPONSE_MAX];
    uint16_t response_length, symbol_index;
    uint32_t touched, reply_started;
    bool owns_transfer, replying;
} f75_bluetooth;

/* Requests contain nonce32, session32, command8, offset16, count16, then
 * optional body bytes. Commands 0..7 are Info, Begin, Read, Patch, Commit,
 * End, Capabilities, Clock. Clock carries seconds since local midnight (u32).
 * Commit carries the complete snapshot CRC32 and an explicit Save flag.
 * Only Commit schedules an application. Nothing programs the radio. */
bool f75_bluetooth_receive(f75_bluetooth *b, f75_transfer *t,
    const uint8_t *request, unsigned length, uint32_t now,
    const f75_config *config, const f75_custom *custom, f75_clock *clock);
void f75_bluetooth_reset(f75_bluetooth *b, f75_transfer *t);
void f75_bluetooth_tick(f75_bluetooth *b, f75_transfer *t, uint32_t now);
/* Emit reset 00, start FF, then seven-bit groups with alternating high bits. Only the
 * descriptor's separate eight-bit data field carries these symbols. */
bool f75_bluetooth_reply_next(f75_bluetooth *b, uint8_t *symbol);
/* Skip embedded record CRC words. CRC(data || CRC(data)) has a fixed residue
 * and therefore cannot identify a particular valid settings snapshot. */
uint32_t f75_bluetooth_snapshot_crc(const uint8_t data[F75_BUNDLE_BYTES]);
