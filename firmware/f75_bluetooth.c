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

/* PackBits-style chunks. Every token consumes input; the caller's fixed reply
 * buffer bounds both the encoded output and each decoded snapshot window. */
static unsigned pack_snapshot(const uint8_t *data, unsigned size, uint8_t *out, unsigned capacity, unsigned *consumed) {
    unsigned at=0, written=0;
    while(at<size && capacity-written>=2) {
        unsigned run=1;
        while(run<128 && at+run<size && data[at+run]==data[at])++run;
        if(run>=3) {out[written++]=(uint8_t)(0x80u| (run-1));out[written++]=data[at];at+=run;}
        else {
            unsigned length=0,limit=capacity-written-1;
            if(limit>128)limit=128;
            while(length<limit && at+length<size) {
                if(length && at+length+2<size && data[at+length]==data[at+length+1] && data[at+length]==data[at+length+2])break;
                ++length;
            }
            out[written++]=(uint8_t)(length-1);memcpy(out+written,data+at,length);written+=length;at+=length;
        }
    }
    *consumed=at;return written;
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
    b->owns_transfer = false; b->replying = false; b->fast = false; b->commit_wait = false;
}

void f75_bluetooth_tick(f75_bluetooth *b, f75_transfer *t, uint32_t now) {
    if (b->owns_transfer && now - b->touched > 20000u) f75_bluetooth_reset(b, t);
    if (b->replying && now - b->reply_started > 12000u) b->replying = false;
}

bool f75_bluetooth_receive(f75_bluetooth *b, f75_transfer *t,
    const uint8_t *q, unsigned size, uint32_t now,
    const f75_config *config, const f75_custom *custom, f75_clock *clock) {
    f75_bluetooth_tick(b, t, now);
    if (size < 13 || size > F75_BT_REQUEST_MAX || b->replying) return false;
    b->fast = false; b->commit_wait = false;
    uint32_t session = get32(q + 4);
    uint8_t command = q[8], status = 0;
    uint16_t offset = get16(q + 9), count = get16(q + 11), length = 0;
    uint8_t *r = b->response;
    memset(r, 0, sizeof(b->response)); memcpy(r, q, 4);
    r[4] = command; put16(r + 7, offset);
    bool body = command == 3 || command == 4 || command == 7;
    if (size != 13u + (body ? count : 0u) || command > 8) status = 3;
    else if (command == 0) {
        if (count || offset) status = 3;
        else { r[11] = 3; put16(r + 12, F75_BUNDLE_BYTES);
            put16(r + 14, F75_BT_READ_MAX); r[16] = F75_BT_PATCH_MAX; length = 6; }
    } else if (command == 6) {
        if (count || offset) status = 3;
        else { r[11] = 1 | (clock ? 2 : 0) | 4; length = 1; } /* Indicators, clock, compressed reads. */
    } else if (command == 7) {
        if (offset || count != 4 || !clock || get32(q + 13) >= 86400u) status = 3;
        else if (b->owns_transfer || t->phase == 1 || t->phase == 2 || t->phase == 3) status = 1;
        else {
            f75_clock_set(clock, get32(q + 13), now);
            put32(r + 11, clock->seconds); length = 4;
        }
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
    } else if (command == 8) {
        if (t->phase != 2) status = 1;
        else if (!count || offset>=F75_BUNDLE_BYTES || count>F75_BUNDLE_BYTES-offset) status = 3;
        else {
            unsigned consumed;
            length=2+pack_snapshot(t->bytes+offset,count,r+13,F75_BT_READ_MAX-2,&consumed);
            put16(r+11,(uint16_t)consumed);
        }
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

static void finish_reply(f75_bluetooth *b, f75_transfer *t, uint8_t status, unsigned length) {
    uint8_t *r=b->response;
    r[5]=status;r[6]=t->phase;put16(r+9,(uint16_t)length);
    put32(r+11+length,f75_crc32(r,11+length));
    b->response_length=(uint16_t)(15+length);b->symbol_index=0;b->replying=true;
}

bool f75_bluetooth_fast_receive(f75_bluetooth *b, f75_transfer *t,
    const uint8_t nonce[4], uint8_t command, uint16_t offset,
    const uint8_t *body, unsigned length, uint32_t now,
    const f75_config *config, const f75_custom *custom) {
    f75_bluetooth_tick(b,t,now);
    if(b->replying||length>F75_BT_PATCH_MAX)return false;
    uint32_t token=get32(nonce);uint8_t status=0;unsigned payload=0;
    memset(b->response,0,sizeof(b->response));memcpy(b->response,nonce,4);
    b->response[4]=command;put16(b->response+7,offset);b->fast=true;b->commit_wait=false;
    if(!token)status=3;
    else if(command==9) {
        if(length||offset>=F75_BUNDLE_BYTES)status=3;
        else if(!offset) {
            if(t->phase==1||t->phase==2||t->phase==3||b->owns_transfer)status=1;
            else {
                f75_bundle_encode(config,custom,t->bytes);t->token=token;t->phase=2;
                t->next=0;t->save=false;b->owns_transfer=true;
            }
        } else if(!b->owns_transfer||t->token!=token)status=4;
        else if(t->phase!=2||offset!=t->next)status=3;
        if(!status) {
            unsigned consumed;
            uint8_t *r=b->response+11;r[0]=1;r[1]=7;
            put32(r+2,f75_bluetooth_snapshot_crc(t->bytes));
            payload=8+pack_snapshot(t->bytes+offset,F75_BUNDLE_BYTES-offset,r+8,F75_BT_READ_MAX-8,&consumed);
            put16(r+6,(uint16_t)consumed);t->next=(uint16_t)(offset+consumed);
            t->touched=now;b->touched=now;
            if(t->next==F75_BUNDLE_BYTES){t->phase=0;t->token=0;b->owns_transfer=false;}
        }
    } else if(command==10) {
        if(offset>1||length<4)status=3;
        else if(t->phase==1||t->phase==2||t->phase==3||b->owns_transfer)status=1;
        else {
            f75_bundle_encode(config,custom,t->bytes);
            if(f75_bluetooth_snapshot_crc(t->bytes)!=get32(body))status=2;
            unsigned at=4,end=0;
            while(!status&&at<length) {
                if(length-at<4){status=3;break;}
                unsigned position=get16(body+at),count=body[at+2];at+=3;
                if(!count||count>length-at||position<end||position>F75_BUNDLE_BYTES-count||
                   (position<F75_RECORD_BYTES&&position+count>F75_RECORD_BYTES-4)||
                   position+count>F75_BUNDLE_BYTES-4){status=3;break;}
                memcpy(t->bytes+position,body+at,count);at+=count;end=position+count;
            }
            if(!status) {
                put32(t->bytes+F75_RECORD_BYTES-4,f75_crc32(t->bytes,F75_RECORD_BYTES-4));
                put32(t->bytes+F75_BUNDLE_BYTES-4,f75_crc32(t->bytes+F75_RECORD_BYTES,F75_BUNDLE_BYTES-F75_RECORD_BYTES-4));
                t->token=token;t->phase=3;t->save=offset!=0;t->touched=now;
                b->owns_transfer=true;b->touched=now;b->commit_wait=true;
            }
        }
    } else status=3;
    finish_reply(b,t,status,payload);b->reply_started=now;return true;
}

void f75_bluetooth_fast_complete(f75_bluetooth *b, f75_transfer *t,
    const f75_config *config, const f75_custom *custom) {
    if(!b->commit_wait||t->phase==3)return;
    uint8_t status=t->phase==7?5:t->phase==6?2:0;
    if(t->phase!=4&&t->phase!=5&&!status)status=4;
    if(!status){f75_bundle_encode(config,custom,t->bytes);put32(b->response+11,f75_bluetooth_snapshot_crc(t->bytes));}
    finish_reply(b,t,status,status?0:4);
    b->commit_wait=false;b->owns_transfer=false;t->phase=0;t->token=0;t->next=0;
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
