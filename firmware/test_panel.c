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
    assert(!f75_render_panel_tile(&view, 135, 240, 239, 8, panel, 1080));
    assert(!f75_render_panel_tile(&view, 135, 240, 0, 8, panel, 1079));
    assert(!f75_render_panel_tile(&view, 240, 135, 0, 8, panel, 1080));
    return 0;
}
