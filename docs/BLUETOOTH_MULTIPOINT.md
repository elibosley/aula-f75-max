# Live Bluetooth switching investigation

The requested behavior is two or three Bluetooth hosts connected at once, with key reports sent only to the selected host. This is not implemented. The current firmware selects one supplier-radio slot and reconnects its saved bond.

## What the current interface establishes

The recovered application sends `A6 31 D7`, `A6 32 D8`, or `A6 33 D9` to select BT1, BT2, or BT3. Keyboard reports use `A1` plus eight report bytes and a checksum. Neither key reports nor the recovered link events include a connection handle. The adapter tracks one selected slot and one connected flag. Keeping three saved bonds does not establish three live links.

No recovered command enables simultaneous links. Commands whose meaning is unqualified must not be relabeled as a multipoint feature. The main MCU image and its recovery stub do not contain or replace the supplier radio firmware. A tested main-MCU recovery path does not prove radio recovery.

## Open-source lead

The [AJAZZ AK820 Pro port](https://github.com/fpb/ajazz-ak820-pro) identifies a CH582F radio and a similar Sonix main MCU. That is evidence about the AK820 Pro, not a verified chip identification for this F75 Max revision.

The [official WCH CH582/CH583 SDK](https://github.com/openwch/ch583/tree/bd508ad7ceed48377619837051412a651952857f/EVT/EXAM/BLE/MultiCentPeri) contains a multiple-connection peripheral example. Its `multiPeripheral.c` tracks connection handles in an array and resumes advertising when capacity remains. The shared [configuration header](https://github.com/openwch/ch583/blob/bd508ad7ceed48377619837051412a651952857f/EVT/EXAM/BLE/HAL/include/config.h) exposes `PERIPHERAL_MAX_CONNECTION`, defaulting to one. This is a plausible development path if the actual board uses a compatible, recoverable radio. It does not prove that the supplier keyboard radio binary supports multipoint, that this PCB has that chip, or that three HID hosts work with the required latency and power budget.

## Required evidence before a radio replacement

1. Identify the actual radio silicon/revision and its programming interface from this board or a matching verified hardware source.
2. Capture its existing firmware, address and bond storage where readable; establish a radio recovery route separately from main-MCU BOOT recovery.
3. Establish the SDK/library limits for two and three peripheral HID links on that chip. The demonstration GATT service is not a finished HID keyboard stack.
4. Implement per-host encryption/bonds, HID protocol and LED state, explicit connection handles, route acknowledgments, and release-before-handoff. Inactive hosts receive releases, not typing. Pairing requires a separate deliberate action.
5. Preserve physical selector priority: a movement cancels a software override; a hardware power cut remains authoritative. Keep USB recovery independent of radio failure.
6. Test with distinct real hosts: all required links stay connected during repeated switching, no stuck modifiers or duplicated typing, no accidental bond replacement, measured handoff delay, and battery-only current/idle/wake behavior. Model-injected UART replies cannot satisfy this check.

This document tracks this as radio development, not a completed keyboard-menu feature.
