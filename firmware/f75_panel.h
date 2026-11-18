#ifndef F75_PANEL_H
#define F75_PANEL_H
#include "f75_display.h"

/* Render the existing 128px UI into a supported physical panel tile.
 * Portrait panels retain native glyphs and sprites, center the content, and
 * anchor the status and footer to the physical panel edges. */
bool f75_render_panel_tile(const f75_view *view, uint16_t width, uint16_t height,
                           uint16_t y, uint8_t rows, uint16_t *pixels, size_t capacity);
#endif
