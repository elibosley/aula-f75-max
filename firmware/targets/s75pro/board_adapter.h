// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
/* S1-2808 V1.10 routine replay; see board-map.json. */
#define F75_PANEL_WIDTH 135
#define F75_PANEL_HEIGHT 240
#define F75_PANEL_OFFSET_X 52
#define F75_PANEL_OFFSET_Y 40
#define F75_PORTRAIT_PANEL 1
#define F75_ENCODER_A B0
#define F75_ENCODER_B A3
#define F75_LED_ROW_COUNT 21
#define F75_LED_SIDE_ROWS A0,A1,A2
#define F75_LED_MASK_A 0x0b07u
/* Stock GPIO init (0x8e70) leaves B0/B1/B18 as inputs. B0 is the
 * encoder. The S75 Caps routine updates key lighting, unlike F75 B1.
 * External NOR wiring has not been qualified; leave A13 untouched. */
#define F75_STOCK_HIGH_PINS A14,A15
#define F75_DEDICATED_CAPS_LED 0
#define F75_EXTERNAL_NOR 0
#define F75_GAUGE_IDLE_HIGH 0
