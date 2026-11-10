// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
#include "f75_bundle.h"
typedef struct {
    uint8_t bytes[F75_BUNDLE_BYTES];
    uint32_t token,expected_crc,touched;
    uint16_t next;
    uint8_t phase; /* 0 idle, 1 upload, 2 snapshot, 3 pending, 4 applied,
                    * 5 saved, 6 invalid, 7 save failed */
    bool save;
} f75_transfer;
bool f75_transfer_receive(f75_transfer *transfer,const uint8_t request[32],uint8_t response[32],uint32_t now,const f75_config *config,const f75_custom *custom);
