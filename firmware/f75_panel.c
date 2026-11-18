#include "f75_panel.h"

bool f75_render_panel_tile(const f75_view *view, uint16_t width, uint16_t height,
                           uint16_t y, uint8_t rows, uint16_t *pixels, size_t capacity) {
    if (!view || !pixels || !rows || rows > F75_TILE_ROWS ||
        !((width == 128 && height == 128) || (width == 135 && height == 240)) ||
        y >= height || rows > height - y || capacity < (size_t)width * rows) return false;
    if (width == 128 && height == 128) return f75_render_tile(view, (uint8_t)y, rows, pixels, capacity);
    if (!view->home && !view->timer) return f75_render_portrait_menu_tile(view, y, rows, pixels, capacity);
    uint16_t background = view->light_mode ? 0xef7b : 0x08a2;
    if (view->alert_pulse) background = view->light_mode ? 0xded6 : 0x2349;
    for (size_t i = 0; i < (size_t)width * rows; ++i) pixels[i] = background;
    const unsigned left = (width - 128) / 2, shift = (height - 128) / 2;
    uint16_t source[128];
    for (unsigned row = 0; row < rows; ++row) {
        unsigned physical = y + row, logical;
        if (physical < 24) logical = physical;
        else if (physical >= height - 16u) logical = physical - (height - 128u);
        else if (physical >= 24u + shift && physical < 112u + shift) logical = physical - shift;
        else continue;
        if (!f75_render_tile(view, (uint8_t)logical, 1, source, 128)) return false;
        for (unsigned x = 0; x < 128; ++x) pixels[row * width + left + x] = source[x];
    }
    return true;
}
