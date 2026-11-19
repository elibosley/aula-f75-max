#include <assert.h>
#include <string.h>
#include "f75_panel.h"

int main(void) {
    f75_view view = {0};
    view.home = true;
    view.face = 3;
    strcpy(view.status_left, "BT2");
    strcpy(view.status_right, "90.58%");
    strcpy(view.clock, "22:33");
    uint16_t original[1024], panel[1082];
    for (unsigned y = 0; y < 128; y += 8) {
        assert(f75_render_tile(&view, y, 8, original, 1024));
        assert(f75_render_panel_tile(&view, 128, 128, y, 8, panel, 1024));
        assert(memcmp(original, panel, sizeof original) == 0);
    }
    for (unsigned y = 0; y < 240; y += 8) {
        panel[0] = 0x1357; panel[1081] = 0x2468;
        assert(f75_render_panel_tile(&view, 135, 240, y, 8, panel + 1, 1080));
        assert(panel[0] == 0x1357 && panel[1081] == 0x2468);
    }
    /* Batched in-place portrait expansion must equal the original per-line
     * renderer even when a tile crosses a status/body/footer boundary. */
    for(unsigned theme=0;theme<2;++theme)for(unsigned face=0;face<4;++face){
        view.light_mode=theme;view.face=face;
        for(unsigned y=0;y<240;++y){
            unsigned rows=240-y<8?240-y:8;
            uint16_t expected[1080],line[128];
            uint16_t background=theme?0xef7b:0x08a2;
            for(unsigned i=0;i<135*rows;++i)expected[i]=background;
            for(unsigned r=0;r<rows;++r){
                unsigned physical=y+r,logical;
                if(physical<24)logical=physical;
                else if(physical>=224)logical=physical-112;
                else if(physical>=80&&physical<168)logical=physical-56;
                else continue;
                assert(f75_render_tile(&view,logical,1,line,128));
                memcpy(expected+r*135+3,line,sizeof(line));
            }
            assert(f75_render_panel_tile(&view,135,240,y,rows,panel,1080));
            assert(!memcmp(expected,panel,135*rows*sizeof(*panel)));
        }
    }
    assert(!f75_render_panel_tile(&view, 135, 240, 239, 8, panel, 1080));
    assert(!f75_render_panel_tile(&view, 135, 240, 0, 8, panel, 1079));
    assert(!f75_render_panel_tile(&view, 240, 135, 0, 8, panel, 1080));
    return 0;
}
