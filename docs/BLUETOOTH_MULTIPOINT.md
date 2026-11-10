# Live Bluetooth switching investigation

The requested behavior is two or three Bluetooth hosts connected at once, with key reports sent only to the selected host. This is not implemented. The current firmware selects one supplier-radio slot. A two-device test confirmed that the previous Bluetooth link disconnects when selecting another slot.

## Closed-case investigation

On 2026-11-10, the operator connected a second host on BT1, then returned to BT2 without pairing again. BT1 disconnected on return. This verifies reconnect-based switching for that test, not simultaneous links or a measured switching delay.

The connected radio reports software revision `2024.07.26 SVN0138`. Its model, manufacturer, hardware and firmware fields contain generic example strings. The exposed services are `180A`, `180F`, `1813` and `FEE0`. Characteristic `FEE1` permits reads and both write modes, but has no notification or indication property.

The [AK820 Pro wireless investigation](https://github.com/jdlien/ak820-pro/blob/f2bb185ce2f306cd52ebc498a675877f06370b15/docs/wireless.md) records the same software revision, placeholder strings and vendor-service properties on a CH582F. This strengthens the CH58x family hypothesis. It does not identify the silicon in this F75 Max revision.

The [official WCH OTA implementation](https://github.com/openwch/ch583/blob/bd508ad7ceed48377619837051412a651952857f/EVT/EXAM/BLE/BackupUpgrade_OTA/APP/peripheral.c) defines a fixed information query. The corresponding host command is 20 bytes: `84 12` followed by 18 zero bytes. A bounded probe sent that information frame through each advertised write mode. Both subsequent reads returned empty data. A later read without another write was also empty. No erase, program, verify, reset or pairing command was sent. The empty replies establish neither a usable update path nor the radio chip identity.

Cached host controller-version metadata and a finite advertisement scan provided no usable chip identification. The inspected updater packages provided no identified radio image. Software investigation can continue with the case closed, but radio replacement remains blocked on identification, firmware access and recovery evidence. No radio replacement has been attempted.

## Connection-status correction

A live BT2 typing check exposed a separate problem: the internal connected flag was false while typing still worked. The ARM regression reproduces one cause: exhausted UART report retries cleared the flag without an RF disconnect event. The correction retains the last known link event across a UART timeout. Explicit disconnects, route changes, pairing requests and report-queue faults still clear the flag. Selection failures still use their separate status and preserve the USB route.

The new regression fails on the prior image and passes on the corrected ARM image. Modeled UART replies verify this state handling, not simultaneous Bluetooth links or physical radio recovery. A missing UART acknowledgment still increments the transport error counter. The diagnostics reader also exposes the existing report-queue fault bit separately.

## What the current interface establishes

The recovered application sends `A6 31 D7`, `A6 32 D8`, or `A6 33 D9` to select BT1, BT2, or BT3. Keyboard reports use `A1` plus eight report bytes and a checksum. Neither key reports nor the recovered link events include a connection handle. The adapter tracks one selected slot and one connected flag. Keeping three saved bonds does not establish three live links.

No recovered command has been verified to enable simultaneous links. Commands whose meaning is unqualified must not be relabeled as a multipoint feature. The main MCU image and its recovery stub do not contain or replace the supplier radio firmware. A tested main-MCU recovery path does not prove radio recovery.

## Open-source lead

The [AJAZZ AK820 Pro port](https://github.com/fpb/ajazz-ak820-pro) identifies a CH582F radio and a similar Sonix main MCU. That is evidence about the AK820 Pro, not a verified chip identification for this F75 Max revision.

The [official WCH CH582/CH583 SDK](https://github.com/openwch/ch583/tree/bd508ad7ceed48377619837051412a651952857f/EVT/EXAM/BLE/MultiCentPeri) contains a multiple-connection peripheral example. Its `multiPeripheral.c` tracks connection handles in an array and resumes advertising when capacity remains. The shared [configuration header](https://github.com/openwch/ch583/blob/bd508ad7ceed48377619837051412a651952857f/EVT/EXAM/BLE/HAL/include/config.h) exposes `PERIPHERAL_MAX_CONNECTION`, defaulting to one. This is a plausible development path if the actual board uses a compatible, recoverable radio. It does not prove that the supplier keyboard radio binary supports multipoint, that this PCB has that chip, or that three HID hosts work with the required latency and power budget.

The example's [actual project configuration](https://github.com/openwch/ch583/blob/bd508ad7ceed48377619837051412a651952857f/EVT/EXAM/BLE/MultiCentPeri/.cproject) explicitly sets `PERIPHERAL_MAX_CONNECTION=3` and `BLE_MEMHEAP_SIZE=10*1024`. This establishes an SDK example configured for three peripheral links. It remains a generic GATT demonstration, not a verified HID implementation for this keyboard.

The three inspected supplier updater packages each contain a 256 KiB main application resource and an embedded archive naming `Settings/FWFiles/SN32F290.hex`. No radio firmware image was identified in those packages. The existing PCB photo shows the radio area, but its top marking is not reliably readable; the package outline alone is insufficient to identify the silicon. Main-MCU firmware restore therefore cannot be treated as a verified radio restore path.

## Required evidence before a radio replacement

1. Identify the actual radio silicon/revision and its programming interface from this board or a matching verified hardware source.
2. Capture its existing firmware, address and bond storage where readable; establish a radio recovery route separately from main-MCU BOOT recovery.
3. Establish the SDK/library limits for two and three peripheral HID links on that chip. The demonstration GATT service is not a finished HID keyboard stack.
4. Implement per-host encryption/bonds, HID protocol and LED state, explicit connection handles, route acknowledgments, and release-before-handoff. Inactive hosts receive releases, not typing. Pairing requires a separate deliberate action.
5. Preserve physical selector priority: a movement cancels a software override; a hardware power cut remains authoritative. Keep USB recovery independent of radio failure.
6. Test with distinct real hosts: all required links stay connected during repeated switching, no stuck modifiers or duplicated typing, no accidental bond replacement, measured handoff delay, and battery-only current/idle/wake behavior. Model-injected UART replies cannot satisfy this check.

This document tracks this as radio development, not a completed keyboard-menu feature.
