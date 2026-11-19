# AULA S75 Pro

This target builds a development firmware candidate. The desktop app identifies the stock USB product as `AULA-S75Pro` at `0c45:800a`. The official driver specifies a 135 × 240 portrait panel and supplies the layout metadata in `layout.json`. That layout describes software key coordinates. The MCU GPIO mapping is recorded separately in `matrix-evidence.json`.

The factory V1.10 image for S1-2808 has SHA-256 `bcc5f633d21f6219b9eebfec2c00b76a4f6bc3246babbe2e157478b26398d598`, a 262144-byte application and checksum `d100`. The update package embeds an SN32F290 family image. These facts establish the research input. The exact installed MCU package and PCB revision remain unverified.

The stock driver was downloaded from the [AULA software page](https://www.aulagaming.com/pages/download). Its S75 Pro installer SHA-256 is `b097008ff9aa4497ca36660e5c61574aca2847500c4263637d236cd92220686b`. The [OEM download page](https://mykeeb.com/downloads/) supplies the S1-2808 V1.10 updater. Vendor executables were extracted as data and were never run. Vendor firmware and executables are excluded from source distribution.

## Simulator

The desktop Firmware and simulator page runs the shared C controls, companion animation and display renderer at the panel's native size. The portrait menu uses the available height with native glyphs. Home keeps its status at the top, centers the companion and clock scene, and anchors the footer to the bottom. The F75 Max retains its 128 × 128 renderer.

The separate bounded routine emulator runs extracted ARM instructions and records GPIO writes, sense inputs, panel initialization commands and orientation offsets. The recovered orientation-zero offsets are 52 columns and 40 rows. Supply the exact factory image to run it.

```sh
.venv/bin/python scripts/emulate_s75.py /path/to/application.bin --output analysis/s75-matrix.json
```

The matrix test stubs GPIO initialization, drive selection during sense testing, and the settle delay. The panel test captures command/data calls while stubbing SPI initialization and timing. It does not execute a complete S75 boot or radio controller. The desktop screen simulation does not establish physical panel initialization, orientation, offsets, SPI timing, or working hardware.

## USB installer

The desktop button loads a bundled release from `firmware/releases/s75pro/`. Release admission checks the target, exact file hashes, image size, validity marker, protected recovery, linked adapter tests and complete ARM system checks. An explicitly optional captured-ROM test may remain unrun. The original private developer flash command retains its stricter captured-ROM requirement.

A release contains `release.json`, `firmware.bin`, `firmware.elf`, `build.json`, `adapter-tests.json` and `system-tests.json`. The release manifest names target `s75pro`, qualification `passed`, SHA-256 hashes for those five payload and receipt files, and the supported original firmware checksums as integer `stock_checksums`. Build metadata names target `s75pro` and display `{"width":135,"height":240}`. Release qualification is a maintainer decision backed by the board's validation evidence.

The installer checks the stock USB product name, requires one USB target, identifies its ROM, checks the installed checksum before erasing, runs the existing verified programming protocol, verifies the programmed checksum, and requests a restart. It writes a private installation receipt and reports failures that need ROM recovery. First installation uses the default custom settings described in the app. Updates from existing custom firmware are outside this initial stock-install path and are rejected by its version check.

No hardware-qualified S75 release is bundled. The linked development candidate and its test instructions are below. The desktop installer remains unavailable until physical validation is complete.

## Linked firmware port

Build the S1-2808 development candidate with the pinned F75 toolchain:

```sh
.venv/bin/python scripts/build_keyboard.py --target s75pro --clean --output-dir analysis/UNFLASHED/s75pro
.venv/bin/python scripts/test_system_emulator.py analysis/UNFLASHED/s75pro/s75pro-wired-test.bin --source-only --output analysis/UNFLASHED/s75pro/system-tests.json
.venv/bin/python scripts/serve_emulator.py analysis/UNFLASHED/s75pro/s75pro-wired-test.bin
```

The target shares the existing SN32 board adapters and portable controls. It omits the F75-only dedicated Caps output and leaves B1/B18/A13 untouched. Caps uses the key RGB indicator. External-NOR diagnostics return unsupported without driving any pins; that optional wiring remains unqualified. Its `board_adapter.h` supplies the portrait geometry, recovered panel offsets, B0/A3 knob inputs and extra A0/A1/A2 LED rows. The generated keymap uses the factory's GPIO scan table and all 80 official software keys, including S75 Home, End and Delete. Fn is matrix position 65; its remapping protection and indicator follow that position. Recovery remains the wheel switch at row 14, column 0. A generated diagnostic mask excludes all typing keys for this model.

The panel adapter sends 16-bit coordinates, including the bottom rows above controller address 255. It draws 30 eight-row tiles with a 32-bit dirty mask. Portrait scene strips render in place without a full framebuffer; the existing F75 menu row cache stays on the F75. The source-only system test checks the complete initialization sequence and every transmitted window and pixel count against the S75 factory setup.

The 18 key color rows retain their shared GPIO grouping. Three additional color rows drive the side lighting through the same 15 PWM columns, using each key column's average color. No CT16B4 PWM channels are enabled: that timer remains the RTOS counter. Physical color order and side-strip direction still require observation.

The shared radio UART initialization matches the S75 factory register writes. The existing transport adapter, gauge reads at address `0x63`, charging input B17 and selector inputs B2/A10 are present in the linked target. Routine replay records their recovered setup and input truth tables. Radio system tests inject UART replies; they do not emulate the radio controller or an RF link. The gauge is not an electrical or battery-life model.

Settings exports identify the model in reserved core metadata byte 130 (0 for F75, 1 for S75). The desktop uses that identifier for key geometry and Fn protection. Record sizes, settings version, host protocol and the shared development USB ID `feed:f750` stay compatible. Product strings distinguish the S75 candidate. New custom settings start with defaults; supplier settings migration is not implemented.

Ordinary MCU idle, dark-screen/PWM shutdown and first-key wake remain enabled. Experimental radio idle commands remain disabled. No deep Stop mode is added by this port. The idle suite keeps the 50 ms modeled input deadline; its full-screen repaint budget is 200 ms for the S75's almost doubled pixel area, versus 100 ms for F75. Emulator timing is not a physical latency measurement.

This is a compiled development candidate, not a hardware-qualified release. No S75 Pro was available. Exact PCB/MCU identification, cold wheel-held ROM recovery, programming/restart, panel appearance, optical LED colors, physical radio pairing/receiver behavior, gauge readings and wake behavior must be checked on an S1-2808 board before admitting a one-click installation release. The source-only ROM check stops at the family recovery boundary and deliberately reports the private captured-ROM test as optional and not run.
