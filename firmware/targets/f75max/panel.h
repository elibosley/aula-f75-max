#pragma once
#include "f75_display.h"
/* Return to matrix/encoder scanning after each bounded 2048-byte pixel slice. */
#define F75_PANEL_TILE_ROWS 8
bool f75_panel_init(void);
bool f75_panel_tile(uint8_t y, uint8_t rows, const uint16_t *pixels);
void f75_panel_backlight(bool enabled);
void f75_panel_performance(uint32_t out[6]);
void f75_panel_bus(uint32_t out[6]);

