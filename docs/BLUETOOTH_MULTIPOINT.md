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

## External-storage probe

The stock display routines also read a separate SPI flash chip through SPI1. A bounded diagnostic probe can read its JEDEC identity or at most 18 bytes at a supplied 24-bit flash offset. The host cannot supply SPI opcodes. The implementation contains only identity (`9F`) and read (`03`) operations, with a transfer deadline and restoration of the peripheral state. Display SPI0 and radio UART2 remain separate.

`scripts/keyboard_storage.py` retrieves these reads into local files. Captures can contain personal display artwork; keep them private. The linked ARM test covers command restrictions, invalid requests, timeout and busy behavior, buffer bounds, and peripheral-state restoration. Synthetic flash responses do not identify the physical chip.

This probe investigates whether the accessible asset storage contains a radio image or updater data. An asset-storage read is not a radio firmware backup, and the probe does not install multipoint support.

## What the current interface establishes

The recovered application sends `A6 31 D7`, `A6 32 D8`, or `A6 33 D9` to select BT1, BT2, or BT3. Keyboard reports use `A1` plus eight report bytes and a checksum. Neither key reports nor the recovered link events include a connection handle. The adapter tracks one selected slot and one connected flag. Keeping three saved bonds does not establish three live links.

No recovered command has been verified to enable simultaneous links. Commands whose meaning is unqualified must not be relabeled as a multipoint feature. The main MCU image and its recovery stub do not contain or replace the supplier radio firmware. A tested main-MCU recovery path does not prove radio recovery.

## Studio over Bluetooth

Temporary Home messages have been physically verified over direct Bluetooth with USB unplugged. Full Studio settings are experimental. The replacement reply channel has passed its hardware qualification and direct Bluetooth Read, Apply, Save and power-cycle checks on the enrolled Mac. The packaged app still needs its own macOS Input Monitoring permission before its window can use the channel. Neither feature requires multiple simultaneous Bluetooth links.

### Requests and temporary status

The enrolled BT2 descriptor is 361 bytes, SHA-256 `34af33fd6776d8cdd456c5d2bd51d40025dd3141564a91333f35b0265e2db584`. Its output report describes keyboard LEDs and padding. The main controller receives changes in that padding through the supplier radio. The experimental sender frames requests with changing two-bit symbols, a start marker and CRC-32. The normal Caps Lock, Num Lock and Scroll Lock bits are preserved.

The operator confirmed a “Bluetooth check” Home message with USB unplugged. Private evidence is retained at `analysis/completion/multipoint/reply-install.Wy8VHmm7/bluetooth-display-confirmation-20261111.json`. Messages require an awake Home screen and expire after their requested duration. Timer and keyboard notices take priority. A successful OS write alone does not prove that a message appeared.

### Retired Fn reply channel

Earlier probes and settings candidates returned bytes in the last field of input report 2, usage page `0x00ff`, usage 3. This was incorrectly treated as a vendor data field. It is the Apple TopCase Fn input. The operator reported unexplained key events during settings tests, so successful data checks from those tests do not establish a usable settings transport.

The main-image hashes beginning `03b41106`, `f1d23336` and `db506b84` are rejected by the flasher. Their immutable failure evidence is retained. Do not reinstall them or use the old reply probes. Radio firmware and saved bonds were not changed.

The [Apple HID event implementation](https://github.com/apple-oss-distributions/IOHIDFamily/blob/main/IOHIDFamily/IOHIDEventService.cpp) handles Apple TopCase keyboard Fn as keyboard input. The [Linux Apple HID driver](https://github.com/torvalds/linux/blob/master/drivers/hid/hid-apple.c) also maps this usage to Fn. A matching data CRC does not make this field safe for arbitrary replies.

### Settings candidate

The installed main-controller candidate is BIN SHA-256 `7409f73279e9e982ad46b2f0535320e22ab855c762c3c359b22d4ad827a99416`, ELF SHA-256 `68cf1ebdf5605a1641470919f3a5600721fded9f2cb43e06e255f21006525f21`. Two clean builds match. Recovery remains `e947b6697eac0759c414416babed8a70212ce501a4d4358ea4396ff47f78a983`. Private admission is `analysis/completion/multipoint/padding-carrier-admission.json`, and installation evidence is `analysis/completion/multipoint/padding-carrier-install-70fryshf/installation.json`. Saved records were preserved. No radio programming was performed.

Protocol 3 replies use byte 1 of input report 2, which the captured descriptor marks Constant. Byte 7, the Fn input, stays zero. Ordinary keys and modifiers are preserved while a reply is sent. A separate bounded probe sends one fixed value and clears it after 50 ms. The host checks raw reports and counts keyboard, modifier and system-key events without recording key codes or typed text. Full settings requests require a private qualification record for the enrolled serial, descriptor and protocol, after all 16 fixed-value probes pass with zero keyboard events.

One earlier Constant-byte probe forwarded its value with clear key fields but observed five global key-down events. The operator confirmed that they were not typing. Its result remains failed and unexplained. A five-second passive control and a later fixed-value probe with additional source diagnostics observed zero keyboard events. These later observations do not erase the earlier failure. A subsequent 16-pattern sweep passed with zero key events. The complete 3232-byte settings read and a reversible RAM change then passed across 32 verified RPCs with zero key, modifier, system-key or raw Fn events. The operator confirmed normal typing, Caps-as-Command, display and lighting without unexplained presses.

`f75_bluetooth` shares the existing settings staging buffer. A session snapshots the complete 3232-byte bundle. Reads return up to 256 bytes, and patches change at most 48 bytes. Commit checks a content fingerprint and both record validators before application. The fingerprint excludes the embedded record CRC fields because complete valid records have a constant CRC residue. An explicit Save flag controls persistence. A stale editor snapshot is rejected, and an unconfirmed Commit is never automatically repeated.

USB settings transfers are excluded while Bluetooth owns the buffer. Physical route changes, disconnects and session timeouts cancel pending work. Replies include the nonce, command, offset, result, phase, length and CRC. Portable and linked ARM checks cover the protocol, ordinary typing preservation, settings, selector failures and power behavior. These checks are separate from physical acceptance.

With USB unplugged, the packaged helper read all 3232 bytes, saved unchanged settings and verified readback. A separate test saved a temporary wheel change. After the operator cut power using the selector, BT2 reconnected without pairing, and the saved core and complete content fingerprint matched. The original wheel mode was then restored and saved over Bluetooth. Private evidence is under `analysis/completion/multipoint/padding-carrier-install-70fryshf/bluetooth-only-settings-sjol3932/`. This is physical transport and persistence evidence. The preview window reported Input Monitoring access as unknown and sent no settings request; its app-level permission and window transfer remain pending.

The installed USB desktop app retains its existing backend. A local Mac Bluetooth preview can be built with `scripts/build_desktop.py --local-bluetooth-preview`; its native helper refuses settings requests without the qualification record. Windows and Linux direct Bluetooth settings are not implemented. Clock synchronization still requires USB. Neither radio firmware nor bonds are part of the settings payload.

The stock application also has a separate 34-byte vendor configuration path for the 2.4 GHz receiver. An offline stock-code test entered that handler only in receiver mode. This does not establish a Bluetooth path or test the physical receiver.

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
