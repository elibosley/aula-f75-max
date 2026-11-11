// SPDX-License-Identifier: GPL-2.0-or-later
#include "f75_bluetooth.h"
#include <string.h>

static uint16_t get16(const uint8_t *p) { return p[0] | ((uint16_t)p[1] << 8); }
static uint32_t get32(const uint8_t *p) {
    return p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}
static void put16(uint8_t *p, uint16_t v) { p[0] = v; p[1] = v >> 8; }
static void put32(uint8_t *p, uint32_t v) {
    for (unsigned i = 0; i < 4; ++i) p[i] = v >> (i * 8);
}

uint32_t f75_bluetooth_snapshot_crc(const uint8_t data[F75_BUNDLE_BYTES]) {
    uint32_t value = UINT32_MAX;
    for (unsigned i = 0; i < F75_BUNDLE_BYTES - 4; ++i) {
        if (i >= F75_RECORD_BYTES - 4 && i < F75_RECORD_BYTES) continue;
        value ^= data[i];
        for (unsigned bit = 0; bit < 8; ++bit)
            value = (value >> 1) ^ ((value & 1u) ? 0xedb88320u : 0u);
    }
    return ~value;
}

void f75_bluetooth_reset(f75_bluetooth *b, f75_transfer *t) {
    if (b->owns_transfer && (t->phase == 2 || t->phase == 3)) {
        t->phase = 0; t->token = 0; t->next = 0;
    }
    b->owns_transfer = false; b->replying = false;
}

void f75_bluetooth_tick(f75_bluetooth *b, f75_transfer *t, uint32_t now) {
    if (b->owns_transfer && now - b->touched > 20000u) f75_bluetooth_reset(b, t);
    if (b->replying && now - b->reply_started > 12000u) b->replying = false;
}

bool f75_bluetooth_receive(f75_bluetooth *b, f75_transfer *t,
    const uint8_t *q, unsigned size, uint32_t now,
    const f75_config *config, const f75_custom *custom) {
    f75_bluetooth_tick(b, t, now);
    if (size < 13 || size > F75_BT_REQUEST_MAX || b->replying) return false;
    uint32_t session = get32(q + 4);
    uint8_t command = q[8], status = 0;
    uint16_t offset = get16(q + 9), count = get16(q + 11), length = 0;
    uint8_t *r = b->response;
    memset(r, 0, sizeof(b->response)); memcpy(r, q, 4);
    r[4] = command; put16(r + 7, offset);
    bool body = command == 3 || command == 4;
    if (size != 13u + (body ? count : 0u) || command > 5) status = 3;
    else if (command == 0) {
        if (count || offset) status = 3;
        else { r[11] = 3; put16(r + 12, F75_BUNDLE_BYTES);
            put16(r + 14, F75_BT_READ_MAX); r[16] = F75_BT_PATCH_MAX; length = 6; }
    } else if (command == 1) {
        if (!session || count || offset) status = 3;
        else if (t->phase == 1 || t->phase == 2 || t->phase == 3 || b->owns_transfer) status = 1;
        else {
            t->token = session; t->phase = 2; t->next = 0; t->save = false;
            t->touched = now; b->touched = now; b->owns_transfer = true;
            f75_bundle_encode(config, custom, t->bytes);
            put32(r + 11, f75_bluetooth_snapshot_crc(t->bytes)); length = 4;
        }
    } else if (!b->owns_transfer || !session || t->token != session) status = 4;
    else if (command == 2) {
        if (t->phase != 2) status = 1;
        else if (!count || count > F75_BT_READ_MAX || offset > F75_BUNDLE_BYTES - count) status = 3;
        else { memcpy(r + 11, t->bytes + offset, count); length = count; }
    } else if (command == 3) {
        if (t->phase != 2) status = 1;
        else if (!count || count > F75_BT_PATCH_MAX || offset > F75_BUNDLE_BYTES - count) status = 3;
        else memcpy(t->bytes + offset, q + 13, count);
    } else if (command == 4) {
        if (t->phase != 2) status = 1;
        else if (offset || count != 5 || q[17] > 1) status = 3;
        else if (f75_bluetooth_snapshot_crc(t->bytes) != get32(q + 13)) status = 2;
        else { t->expected_crc = get32(q + 13); t->save = q[17]; t->phase = 3; }
    } else if (command == 5) {
        if (offset || count) status = 3;
        else if (t->phase == 3) status = 1;
        else { b->owns_transfer = false; t->phase = 0; t->token = 0; t->next = 0; }
    }
    if (!status && b->owns_transfer && session == t->token) {
        b->touched = now; t->touched = now;
    }
    r[5] = status; r[6] = t->phase; put16(r + 9, length);
    put32(r + 11 + length, f75_crc32(r, 11 + length));
    b->response_length = 15 + length; b->symbol_index = 0;
    b->reply_started = now; b->replying = true;
    return true;
}

bool f75_bluetooth_reply_next(f75_bluetooth *b, uint8_t *symbol) {
    if (!b->replying) return false;
    // Reset the data field before FF. A prior frame can itself end in FF,
    // and unchanged HID element values need not generate a second event.
    if (b->symbol_index < 2) {
        *symbol = b->symbol_index ? 0xff : 0;
        ++b->symbol_index; return true;
    }
    unsigned group = b->symbol_index - 2, bit = group * 7;
    if (bit >= b->response_length * 8u) { b->replying = false; return false; }
    uint8_t value = 0;
    for (unsigned i = 0; i < 7 && bit + i < b->response_length * 8u; ++i)
        value |= ((b->response[(bit + i) / 8] >> ((bit + i) % 8)) & 1u) << i;
    *symbol = value | ((group & 1u) << 7); ++b->symbol_index;
    return true;
}
