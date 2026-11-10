#ifndef F75_LIGHTING_H
#define F75_LIGHTING_H
#include "f75_core.h"
enum { F75_LIGHT_ROWS=6,F75_LIGHT_COLS=15,F75_LIGHT_BYTES=270 };
/* Planar, 7-bit PWM values: channel * 90 + row * 15 + column.
 * Pure/reentrant; used by the board and the native preview. */
void f75_lighting_frame(const f75_config *config,uint8_t brightness,uint32_t now,uint8_t output[F75_LIGHT_BYTES]);
#endif
