// SPDX-License-Identifier: GPL-2.0-or-later
#include "f75_bluetooth.h"
#include "f75_bluetooth_dictionary.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

static f75_bluetooth b;
static f75_transfer t;
static f75_config c;
static f75_custom custom;
static f75_clock clock;
static uint32_t now = 100;

static void put32(uint8_t *p, uint32_t n) { for (unsigned i = 0; i < 4; ++i) p[i] = n >> (8 * i); }
static uint8_t request(unsigned command, unsigned offset, unsigned count, const uint8_t *body, uint32_t token) {
    uint8_t q[64] = {0x17, 0x29, 0x45, 0x9a};
    put32(q + 4, token); q[8] = command; q[9] = offset; q[10] = offset >> 8;
    q[11] = count; q[12] = count >> 8;
    unsigned size = 13;
    if (body) { assert(count <= 51); memcpy(q + 13, body, count); size += count; }
    assert(f75_bluetooth_receive(&b, &t, q, size, ++now, &c, &custom, &clock));
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
    assert(request(6, 0, 0, NULL, 0) == 0 && b.response[11] == 7);
    assert(request(6, 1, 0, NULL, 0) == 3);
    uint8_t seconds[4]; put32(seconds, 86399);
    assert(request(7, 0, 4, seconds, 0) == 0 && clock.valid && clock.seconds == 86399);
    assert(!memcmp(b.response + 11, seconds, 4) && !b.owns_transfer && t.phase == 0);
    put32(seconds, 86400);
    assert(request(7, 0, 4, seconds, 0) == 3 && clock.seconds == 86399);
    put32(seconds, 0);
    assert(request(7, 1, 4, seconds, 0) == 3 && clock.seconds == 86399);
    assert(request(7, 0, 3, seconds, 0) == 3 && clock.seconds == 86399);
    assert(request(7, 0, 4, NULL, 0) == 3 && clock.seconds == 86399);
    t.phase = 1;
    assert(request(7, 0, 4, seconds, 0) == 1 && clock.seconds == 86399);
    t.phase = 0;
    assert(request(7, 0, 4, seconds, 0) == 0 && clock.seconds == 0);
    assert(request(1, 0, 0, NULL, 0) == 3);
    assert(request(1, 0, 0, NULL, 21) == 0 && t.phase == 2);
    assert(request(7, 0, 4, seconds, 21) == 1 && t.phase == 2 && b.owns_transfer);
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
    /* Decode the actual framed compressed replies, including a dense worst
     * case. Existing raw Read remains available to explicitly older clients. */
    for(unsigned pattern=0;pattern<5;++pattern){
        if(pattern)for(unsigned i=0;i<F75_BUNDLE_BYTES;++i)t.bytes[i]=(uint8_t)(pattern==1?0:pattern==2?i:pattern==3?i/127:i*73u+(i>>3));
        unsigned offset=0,windows=0;
        while(offset<F75_BUNDLE_BYTES){
            assert(request(8,offset,F75_BUNDLE_BYTES-offset,NULL,21)==0);
            unsigned count=b.response[11]|((unsigned)b.response[12]<<8),at=13,decoded=0,end=b.response_length-4;
            assert(count && count<=F75_BUNDLE_BYTES-offset && end<=267);
            while(at<end){
                unsigned token=b.response[at++],length=(token&127u)+1;
                assert(length<=count-decoded);
                if(token&128u){assert(at<end);for(unsigned i=0;i<length;i++)assert(t.bytes[offset+decoded++]==b.response[at]);++at;}
                else {assert(length<=end-at);for(unsigned i=0;i<length;i++)assert(t.bytes[offset+decoded++]==b.response[at++]);}
            }
            assert(decoded==count);offset+=count;++windows;
        }
        if(pattern==1)assert(windows==1);
    }
    assert(request(8,0,0,NULL,21)==3);
    assert(request(8,F75_BUNDLE_BYTES,1,NULL,21)==3);
    memcpy(t.bytes,initial,sizeof(initial));
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
    assert(!f75_bluetooth_receive(&b, &t, short_request, sizeof(short_request), ++now, &c, &custom, &clock));
    /* Atomic fast requests use the same guarded transfer and reply framing. */
    f75_bluetooth_reset(&b,&t);t.phase=0;
    uint8_t nonce[4]={0x12,0x34,0x56,0x78};unsigned position=0;
    f75_bundle_encode(&c,&custom,initial);
    do {
        assert(f75_bluetooth_fast_receive(&b,&t,nonce,9,position,NULL,0,++now,&c,&custom));
        assert(b.fast&&!b.response[5]&&b.response[11]==1&&b.response[12]==7);
        unsigned count=b.response[17]|((unsigned)b.response[18]<<8),at=19,decoded=0;
        assert(count&&count<=F75_BUNDLE_BYTES-position);
        while(at<b.response_length-4u){
            unsigned token=b.response[at++],length=(token&127u)+1;
            assert(length<=count-decoded);
            if(token&128u){for(unsigned i=0;i<length;++i)assert(initial[position+decoded++]==b.response[at]);++at;}
            else for(unsigned i=0;i<length;++i)assert(initial[position+decoded++]==b.response[at++]);
        }
        assert(decoded==count);position+=count;b.replying=false;
    }while(position<F75_BUNDLE_BYTES);
    assert(!b.owns_transfer&&t.phase==0);
    /* Extended zero spans are requested explicitly; reconstruct every byte,
     * including the embedded record CRCs, through the actual C encoder. */
    uint8_t codec=2;position=0;unsigned compact_wire=0;
    do {
        assert(f75_bluetooth_fast_receive(&b,&t,nonce,9,position,&codec,1,++now,&c,&custom));
        assert(!b.response[5]&&b.response[11]==2);
        unsigned count=b.response[17]|((unsigned)b.response[18]<<8),at=19,decoded=0;
        while(at<b.response_length-4u) {
            unsigned token=b.response[at++],length=(token&127u)+1;
            if(token==128) {
                assert(at+2<=b.response_length-4u);length=b.response[at]|((unsigned)b.response[at+1]<<8);at+=2;
                assert(length&&length<=count-decoded);
                for(unsigned i=0;i<length;++i)assert(initial[position+decoded++]==0);
            } else {
                assert(length<=count-decoded);
                if(token&128u){for(unsigned i=0;i<length;++i)assert(initial[position+decoded++]==b.response[at]);++at;}
                else for(unsigned i=0;i<length;++i)assert(initial[position+decoded++]==b.response[at++]);
            }
        }
        assert(count==decoded);position+=count;compact_wire+=b.response_length;b.replying=false;
    }while(position<F75_BUNDLE_BYTES);
    assert(compact_wire<160&&!b.owns_transfer&&t.phase==0);
    for(unsigned i=0;i<F75_BUNDLE_BYTES;++i)assert(initial[i]==f75_bt_dictionary3_byte(i));
    codec=3;
    assert(f75_bluetooth_fast_receive(&b,&t,nonce,9,0,&codec,1,++now,&c,&custom));
    assert(!b.response[5]&&b.response[11]==3&&b.response_length==26);
    assert(b.response[19]==128&&(b.response[20]|((unsigned)b.response[21]<<8))==F75_BUNDLE_BYTES);
    assert(!b.owns_transfer&&t.phase==0);b.replying=false;
    codec=4;
    assert(f75_bluetooth_fast_receive(&b,&t,nonce,9,0,&codec,1,++now,&c,&custom)&&b.response[5]==3&&!b.owns_transfer);b.replying=false;
    uint8_t small[6];put32(small,f75_bluetooth_snapshot_crc(initial));small[4]=8;small[5]=1;
    assert(f75_bluetooth_fast_receive(&b,&t,nonce,10,0,small,6,++now,&c,&custom)&&b.response[5]==3&&t.phase==0);b.replying=false;
    small[4]=119;
    assert(f75_bluetooth_fast_receive(&b,&t,nonce,10,0,small,6,++now,&c,&custom)&&t.phase==3);
    assert(f75_bundle_decode(t.bytes,&c,&custom)&&c.wheel==1);t.phase=4;f75_bluetooth_fast_complete(&b,&t,&c,&custom);b.replying=false;
    f75_bundle_encode(&c,&custom,other);put32(small,f75_bluetooth_snapshot_crc(other));small[5]=0;
    assert(f75_bluetooth_fast_receive(&b,&t,nonce,10,0,small,6,++now,&c,&custom)&&t.phase==3);
    assert(f75_bundle_decode(t.bytes,&c,&custom)&&c.wheel==0);t.phase=4;f75_bluetooth_fast_complete(&b,&t,&c,&custom);b.replying=false;
    uint8_t atomic[8]={0};put32(atomic,f75_bluetooth_snapshot_crc(initial));atomic[4]=119;atomic[6]=1;atomic[7]=1;
    uint8_t stale[8];memcpy(stale,atomic,8);stale[0]^=1;
    assert(f75_bluetooth_fast_receive(&b,&t,nonce,10,0,stale,8,++now,&c,&custom)&&b.response[5]==2&&t.phase==0);b.replying=false;
    assert(f75_bluetooth_fast_receive(&b,&t,nonce,10,0,atomic,8,++now,&c,&custom)&&!b.response[5]&&t.phase==3&&b.commit_wait);
    f75_bluetooth_fast_complete(&b,&t,&c,&custom);assert(b.commit_wait&&t.phase==3);
    assert(f75_bundle_decode(t.bytes,&c,&custom)&&c.wheel==1);t.phase=4;
    f75_bluetooth_fast_complete(&b,&t,&c,&custom);assert(!b.commit_wait&&!b.owns_transfer&&t.phase==0&&b.response[6]==4&&b.response_length==19);
    f75_bundle_encode(&c,&custom,other);uint32_t actual;memcpy(&actual,b.response+11,4);assert(actual==f75_bluetooth_snapshot_crc(other));b.replying=false;
    put32(atomic,actual);atomic[4]=156;
    assert(f75_bluetooth_fast_receive(&b,&t,nonce,10,0,atomic,8,++now,&c,&custom)&&b.response[5]==3&&t.phase==0);b.replying=false;
    atomic[4]=119;atomic[7]=0;
    assert(f75_bluetooth_fast_receive(&b,&t,nonce,10,1,atomic,8,++now,&c,&custom)&&t.save&&b.commit_wait);
    t.phase=7;f75_bluetooth_fast_complete(&b,&t,&c,&custom);assert(b.response[5]==5&&b.response[6]==7&&!b.owns_transfer);b.replying=false;
    assert(f75_bluetooth_fast_receive(&b,&t,nonce,10,2,atomic,8,++now,&c,&custom)&&b.response[5]==3);b.replying=false;
    t.phase=2;t.token=100;
    assert(f75_bluetooth_fast_receive(&b,&t,nonce,9,0,NULL,0,++now,&c,&custom)&&b.response[5]==1);b.replying=false;t.phase=0;
    assert(f75_bluetooth_fast_receive(&b,&t,nonce,9,1,NULL,0,++now,&c,&custom)&&b.response[5]==4);b.replying=false;
    puts("Bluetooth settings sessions, bounds, commit guard, cancellation and reply framing passed.");
}
