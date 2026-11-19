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
/* B0 is the encoder input on this board. Never drive it low. */
#define F75_STOCK_LOW_PINS B1,B18
#define F75_GAUGE_IDLE_HIGH 0
