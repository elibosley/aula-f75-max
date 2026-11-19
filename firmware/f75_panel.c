#include "f75_panel.h"
#include <string.h>

static bool logical_row(unsigned physical,unsigned height,unsigned shift,unsigned *logical){
    if(physical<24)*logical=physical;
    else if(physical>=height-16)*logical=physical-(height-128);
    else if(physical>=24+shift&&physical<112+shift)*logical=physical-shift;
    else return false;
    return true;
}
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
    for(unsigned row=0;row<rows;){
        unsigned logical;
        if(!logical_row(y+row,height,shift,&logical)){++row;continue;}
        unsigned count=1,next;
        while(row+count<rows&&logical_row(y+row+count,height,shift,&next)&&next==logical+count)++count;
        /* Render each contiguous scene strip once. Expand its compact 128px
         * rows backwards in the caller's tile; no extra framebuffer or stack
         * tile, and no repeated sprite decoding for each physical scanline. */
        uint16_t *strip=pixels+row*width;
        if(!f75_render_tile(view,(uint8_t)logical,(uint8_t)count,strip,capacity-row*width))return false;
        for(unsigned r=count;r>0;--r){
            uint16_t *destination=strip+(r-1)*width;
            memmove(destination+left,strip+(r-1)*128,128*sizeof(*pixels));
            for(unsigned x=0;x<left;++x)destination[x]=background;
            for(unsigned x=left+128;x<width;++x)destination[x]=background;
        }
        row+=count;
    }
    return true;
}
