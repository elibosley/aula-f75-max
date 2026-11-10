// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
#include "f75_custom.h"
enum {F75_BUNDLE_BYTES=F75_RECORD_BYTES+F75_CUSTOM_BYTES,F75_ENVELOPE_BYTES=4096};
void f75_bundle_encode(const f75_config *config,const f75_custom *custom,uint8_t out[F75_BUNDLE_BYTES]);
bool f75_bundle_decode(const uint8_t in[F75_BUNDLE_BYTES],f75_config *config,f75_custom *custom);
void f75_envelope_encode(const f75_config *config,const f75_custom *custom,uint32_t generation,uint8_t out[F75_ENVELOPE_BYTES]);
bool f75_envelope_decode(const uint8_t in[F75_ENVELOPE_BYTES],f75_config *config,f75_custom *custom,uint32_t *generation);
