# F75 Max custom firmware and editor

The keyboard runs the custom ARM firmware. Use the [deployment record](../analysis/hardware-deployment-status.json) for the installed image, flash receipt, live checksum, and physical acceptance. The [completion queue](../analysis/completion/status.json) preserves unfinished work. A passing emulator check does not establish an RF connection, battery endurance, LED color order, or cold recovery.

## Three surfaces

- [Your keyboard](http://127.0.0.1:8787/hardware.html) reads and changes the actual keyboard through its USB diagnostics interface. The physical selector can remain on Bluetooth. **Apply** changes RAM; **Save to keyboard** also writes flash. Both paths read the settings back.
- [Native preview](http://127.0.0.1:8787/) runs the portable C core and pixel renderer with simulated hardware. Its browser profile is separate from the real keyboard.
- [ARM emulator](http://127.0.0.1:8788/) runs the linked image from reset through ChibiOS, interrupts, USB, the matrix and SPI writes. Its peripheral electronics and radio responses are modeled. The page reports its exact image hash.

The Mac must be awake, connected to Tailscale, and running the corresponding service. The editor needs the keyboard's USB cable; browser actions on the phone go through that Mac. Browser sessions do not grant arbitrary memory, boot-option, radio-firmware or host-key injection access.

## Onboard controls

Turn the wheel for the Home action or a menu selection. The first detent moves immediately. Press to open/select. Hold for 650 ms to go Back while still held; release does not add a click. Pairing has its separate 1.2-second confirmation.

Lighting brightness/speed edit one point on slow turns and three points after four rapid turns in the same direction. Reversal returns to one-point steps. Values stop at their bounds. Motion does not delay input. Reduced motion snaps transitions to their final position.

Hold Fn+Space for the Control layer. Use 1–5 for Devices, Keys, Lighting, Power and Focus; arrows/J/K navigate, Enter selects, Escape goes Back, S saves. Fn+M chooses a manual Mac/Windows layout. Keys → Layout cycles Auto, Mac and Windows.

Fn+1/2/3 select Bluetooth slots, Fn+4 requests the receiver, Fn+5 requests USB. A physical selector movement cancels that temporary override and selects its physical mode. A restart follows the selector. Plugging in a cable alone does not replace a wireless route. Requests require an available powered transport; software cannot overcome the reported battery power cut in the middle position without USB power.

Fn+P opens pairing for the current Bluetooth slot. Hold the wheel 1.2 seconds to confirm replacement of its existing bond. Fn+Escape cancels the pairing dialog. Switching never pairs. Outside pairing, held Fn+Escape requests ROM recovery. The protected startup wheel scan remains intact; physical cold wheel-held recovery is still pending acceptance.

## Layouts, macros and colors

Caps exchanges with physical left Ctrl in every OS profile. Mac mode then converts Control to Command: Caps sends Command, physical left Ctrl sends Caps Lock, and right Ctrl sends right Command. Windows and Android keep Control as Control. Mac mode also exchanges Alt and GUI. Every physical release uses the action captured on press; route/layout changes release existing owners first.

The header shows an Apple, Windows or Android mark with Auto, Manual or Saved. Keys → Layout cycles Auto, manual Mac, manual Windows and manual Android for the selected device. USB can identify Apple and Windows hosts; the current USB fingerprint cannot distinguish Android from Linux, so those ambiguous hosts retain their saved profile. Bluetooth uses verified helper evidence when available. Android can always be selected manually.

The editor exposes Base and Fn key mappings and Base, Fn and Control lighting layers. Fn, the wheel and built-in Fn recovery/device shortcuts are reserved. Custom mappings are logical HID actions; Original action retains the global physical Caps/Ctrl and Mac/Windows mapping. Consumer actions and mouse clicks/scrolling are supported.

Eight macro slots hold at most 32 press/release/wait steps each. Primary resolves to Command on Mac and Ctrl on Windows. Presses must be balanced by releases; overlapping aliases and more than six ordinary held keys are rejected. Repeat runs while the trigger is held and finishes its current cycle after release. Upload and restart never run a macro. Route changes, disconnect, configuration apply and recovery cancel playback and release its keys without releasing a physical key's separate ownership.

Per-key colors override their current layer color. Without a layer color, an inherited key can use its Base color; otherwise the existing effect supplies its color. Black means off, while Inherit removes the override. Brightness and power limits apply to every layer. Physical key/color correspondence still needs visual acceptance.

## OS detection and clock

USB uses QMK's host-enumeration fingerprint, with manual overrides available. USB evidence only changes the USB profile. It never identifies another Bluetooth host by itself.

The optional [host helper](../scripts/host_helper.py) enumerates only the target USB/Bluetooth/dongle identities. It never registers typing callbacks or reads keyboard input reports. An enrolled wireless serial identity must match the current USB board, active slot and connected local device. Firmware also checks its current connection transaction and Auto flag when queuing and applying a hint. Manual layouts, stale hints, another slot, pairing and disconnected devices are rejected. The display says Auto only after accepted evidence; otherwise it says Saved. The helper does not save flash automatically.

The helper works while USB is attached. Its cabled Mac path can identify this Mac as the host of its enrolled BT slot. Windows metadata support is implemented but needs Windows hardware acceptance. Bluetooth HID access was denied by macOS in the direct-channel probe; no extra permission is needed for the cabled metadata path. Wholly wireless OS/time delivery is not implemented. The radio firmware and its bonds are not rewritten.

The clock receives local seconds since midnight and then advances on elapsed milliseconds. The editor's **Sync clock** uses the phone/browser's local time. The helper uses the Mac's local time, resyncs an invalid clock after restart, refreshes hourly, and detects timezone or wall-clock jumps while available. No RTC power-off retention is claimed. Chibi remains the default; the editor also selects Minimal, Orbit and Constellation clock faces.

The optional [Mac wireless probe](../scripts/mac_wireless_probe.m) is a separate, locally built app for testing a possible Bluetooth LED-output channel. It matches an enrolled device, checks macOS access, and registers no input callbacks. Its default check opens no device. Explicit test modes require macOS Input Monitoring access and can briefly change and restore the Num Lock output; they send no keyboard input. This channel is unproven, so fully wireless OS/time delivery is not installed. The working cabled helper remains the automatic path.

Run a bounded helper check from the project root:

```sh
.venv/bin/python scripts/host_helper.py --dry-run
.venv/bin/python scripts/host_helper.py --watch-seconds 10
```

Enrollment is a separate explicit association with the physically confirmed device, using `--enroll 1` (or 2/3/4) while that slot is selected and locally connected. Bindings store hashed identities privately in `.runtime/host-bindings.json`. They are not sent to a web service. `--dry-run` suppresses device writes; combining it with `--enroll` still saves that local association.

## Durable settings

The 115-byte portable configuration encodes into a version-4, 160-byte `F75S` record. `F75C` contains the key maps, macros and layer colors in 3072 bytes. A 4096-byte `F75X` envelope adds generation and CRC32 around both. The board alternates reserved records at `0x38000` and `0x39000`, writes CRC last and verifies the complete record. Unchanged valid settings do not wear flash again. A corrupt active CRC is repaired through the other record.

Legacy records at `0x3f000` and `0x3f400` migrate without being overwritten. Build admission requires both new regions and legacy pages to be explicitly erased in the canonical image. Flash updates must capture and merge those fixed regions; the programmed payload hash/live checksum differ from the archived blank-settings image.

Save, restart, torn writes, invalid configuration and CRC corruption have ARM tests. Actual Save and ROM restart preserved identical expanded record bytes with zero flash errors. Cold-power retention and preservation through each later update are recorded separately in the completion queue. Settings captures and source identities must be fresh before programming.

## Power and display

The read-only recovered battery gauge supplies measured voltage and percentage. Failed/stale measurements display unknown rather than an invented value. USB enumeration proves external power for the policy; an unenumerated wall charger is conservatively treated as battery. No gauge configuration or radio firmware is written.

Balanced dims after 15 seconds and turns the screen/RGB off after 45; Endurance is quieter and faster to dim, while Desk stays active longer. At 10% battery, animation stops and brightness is capped; at 5%, RGB turns off. The display backlight currently has on/off control only. Display wake waits for a fresh complete frame.

With the display off, the main task yields for 1 ms so ChibiOS can wait for interrupts. The shared key/LED row clock uses a 511-tick period instead of 255, the three LED PWM timers stop, and unchanged dark color frames are skipped. Raw key changes restore the active budget before debounce; Fn and the wheel button also wake it. USB, radio and key scanning remain available. This is shallow CPU idle, not deep MCU or radio Stop mode. Current draw and battery endurance remain unmeasured.

The display remains native 128×128 RGB565, with 10-pixel bold status text, 11-pixel bold menu labels, and 27-pixel semibold Inter clock digits and 80×80 chibi art. Rendering uses 2048-byte tiles. SPI is 8-bit at 8 MHz; each selected byte waits for RX and BUSY completion while only the shared CT16B3 matrix/LED IRQ is deferred. Timer1's match-control register is unkeyed; preserving that distinction resolved the accepted RGB flicker. Do not remove either fix.

The chibi uses tap counts and elapsed time, with no retained text. A small analog clock sits on her desk. The idle Home screen has no menu hint or Auto/Manual label. The focus timer runs 25-minute work sessions, five-minute short breaks and a 15-minute break after four completed work sessions. Completion wakes the screen and gives gentle pulses; reduced motion suppresses them. Speaker support, physical timer accuracy and wake current remain unqualified.

## Build and verification

See the [target guide](targets/f75max/README.md). Keep source tests, exact linked-image tests, simulator results, programming verification and physical acceptance separate. Current image receipts include full ARM-system execution without function stubs plus focused checks for settings, OS, radio, display, power/scroll, customization and host evidence.

## Mac helper service

This Mac's enrolled BT1 helper runs as `com.elibosley.f75-host-helper`. Its LaunchAgent starts at user login, runs one instance, and does not restart completed jobs. It waits while USB is absent, refreshes only missing/changed host evidence, and performs no automatic Save. The log is `.runtime/host-helper.log`; no raw serial identities or typing are logged. It uses the same bounded transport lock as the editor and diagnostic tools.

Inspect the installed service with `launchctl print gui/$(id -u)/com.elibosley.f75-host-helper`. To stop it gracefully, use `launchctl kill SIGTERM gui/$(id -u)/com.elibosley.f75-host-helper`, verify that exact process has exited, then boot out its plist under `~/Library/LaunchAgents/`. Removing the plist prevents future login starts. This is an application service, not a Codex completion waiter; it never queues thread messages.
