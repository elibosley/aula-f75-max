// SPDX-License-Identifier: GPL-2.0-or-later
#include QMK_KEYBOARD_H
#include "power.h"
#include "battery.h"
#include "usb_main.h"
#include "f75_usb_link.h"
static f75_usb_link usb_link;
bool f75_board_usb_active(uint32_t now){
    /* SN32 USB_FRMNO (offset 0x60) updates only on a received host SOF.
     * Read the existing hardware counter; no extra USB interrupt is enabled. */
    return f75_usb_link_observe(&usb_link,USB_DRIVER.state==USB_ACTIVE,
        (uint16_t)usbGetFrameNumberX(&USB_DRIVER),now);
}
f75_budget f75_board_power_budget(const f75_state *state,uint32_t now){
    uint8_t percent=100;
    (void)f75_battery_percent(&percent);
    /* A live configured USB link proves external power. An unenumerated charger
     * is treated conservatively as battery operation until VBUS is mapped. */
    return f75_power_budget(state,now,percent,f75_board_usb_active(now));
}
