// SPDX-License-Identifier: GPL-2.0-or-later
#include QMK_KEYBOARD_H
#include "power.h"
#include "battery.h"
#include "usb_main.h"
f75_budget f75_board_power_budget(const f75_state *state,uint32_t now){
    uint8_t percent=100;
    (void)f75_battery_percent(&percent);
    /* A configured USB link proves external power. An unenumerated charger
     * is treated conservatively as battery operation until VBUS is mapped. */
    return f75_power_budget(state,now,percent,USB_DRIVER.state==USB_ACTIVE);
}
