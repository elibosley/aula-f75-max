// SPDX-License-Identifier: GPL-2.0-or-later
#include "f75_bluetooth.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

static f75_bluetooth b;
static f75_transfer t;
static f75_config c;
static f75_custom custom;
static uint32_t now = 100;

static void put32(uint8_t *p, uint32_t n) { for (unsigned i = 0; i < 4; ++i) p[i] = n >> (8 * i); }
static uint8_t request(unsigned command, unsigned offset, unsigned count, const uint8_t *body, uint32_t token) {
    uint8_t q[64] = {0x17, 0x29, 0x45, 0x9a};
    put32(q + 4, token); q[8] = command; q[9] = offset; q[10] = offset >> 8;
    q[11] = count; q[12] = count >> 8;
    unsigned size = 13;
    if (body) { assert(count <= 51); memcpy(q + 13, body, count); size += count; }
    assert(f75_bluetooth_receive(&b, &t, q, size, ++now, &c, &custom));
    uint8_t decoded[F75_BT_RESPONSE_MAX] = {0}, symbol, previous = 0;
    unsigned groups = 0, bit = 0;
    assert(f75_bluetooth_reply_next(&b, &symbol) && symbol == 0);
    assert(f75_bluetooth_reply_next(&b, &symbol) && symbol == 255); previous = symbol;
    while (f75_bluetooth_reply_next(&b, &symbol)) {
        assert(symbol != previous); previous = symbol;
        assert((symbol >> 7) == (groups++ & 1u));
        for (unsigned i = 0; i < 7 && bit < b.response_length * 8u; ++i, ++bit)
            decoded[bit / 8] |= ((symbol >> i) & 1u) << (bit % 8);
    }
    assert(bit == b.response_length * 8u);
    assert(!memcmp(decoded, b.response, b.response_length));
    assert(!memcmp(decoded, q, 4) && decoded[4] == command);
    uint32_t crc; memcpy(&crc, decoded + b.response_length - 4, 4);
    assert(crc == f75_crc32(decoded, b.response_length - 4));
    return decoded[5];
}

int main(void) {
    f75_defaults(&c); f75_custom_defaults(&custom);
    assert(request(0, 0, 0, NULL, 0) == 0 && b.response[11] == 3);
    assert(request(1, 0, 0, NULL, 0) == 3);
    assert(request(1, 0, 0, NULL, 21) == 0 && t.phase == 2);
    uint8_t initial[F75_BUNDLE_BYTES]; memcpy(initial, t.bytes, sizeof(initial));
    f75_config other_config=c; other_config.wheel=1;
    uint8_t other[F75_BUNDLE_BYTES]; f75_bundle_encode(&other_config,&custom,other);
    assert(f75_crc32(initial,sizeof(initial))==f75_crc32(other,sizeof(other)));
    assert(f75_bluetooth_snapshot_crc(initial)!=f75_bluetooth_snapshot_crc(other));
    assert(request(1, 0, 0, NULL, 22) == 1);
    assert(request(2, 0, 256, NULL, 22) == 4);
    assert(request(2, 0, 256, NULL, 21) == 0);
    assert(b.response_length == F75_BT_RESPONSE_MAX && !memcmp(b.response + 11, initial, 256));
    assert(request(2, F75_BUNDLE_BYTES - 1, 256, NULL, 21) == 3);
    assert(request(2, 0, 257, NULL, 21) == 3);
    assert(request(3, F75_BUNDLE_BYTES - 1, 2, (uint8_t[]){1, 2}, 21) == 3);
    uint8_t patch = 1;
    assert(request(3, 119, 1, &patch, 21) == 0 && t.bytes[119] == 1);
    assert(c.wheel == 0); /* Patching never applies a partial snapshot. */
    uint8_t commit[5] = {0};
    assert(request(4, 0, 5, commit, 21) == 2 && t.phase == 2);
    put32(commit, f75_bluetooth_snapshot_crc(t.bytes)); commit[4] = 2;
    assert(request(4, 0, 5, commit, 21) == 3 && t.phase == 2);
    commit[4] = 0;
    assert(request(4, 0, 5, commit, 21) == 0 && t.phase == 3 && !t.save);
    assert(request(5, 0, 0, NULL, 21) == 1);
    f75_bluetooth_reset(&b, &t); assert(t.phase == 0 && !b.owns_transfer);
    assert(request(1, 0, 0, NULL, 31) == 0);
    f75_bluetooth_tick(&b, &t, now + 20001); assert(t.phase == 0 && !b.owns_transfer);
    now += 21000;
    assert(request(1, 0, 0, NULL, 41) == 0);
    memcpy(t.bytes, initial, sizeof(initial)); put32(commit, f75_bluetooth_snapshot_crc(t.bytes)); commit[4] = 1;
    assert(request(4, 0, 5, commit, 41) == 0 && t.phase == 3 && t.save);
    t.phase = 5; /* The board adapter has completed its explicit flash Save. */
    f75_bluetooth_reset(&b, &t); assert(t.phase == 5);
    t.phase = 1; assert(request(1, 0, 0, NULL, 51) == 1); t.phase = 0;
    uint8_t short_request[12] = {0};
    assert(!f75_bluetooth_receive(&b, &t, short_request, sizeof(short_request), ++now, &c, &custom));
    puts("Bluetooth settings sessions, bounds, commit guard, cancellation and reply framing passed.");
}
