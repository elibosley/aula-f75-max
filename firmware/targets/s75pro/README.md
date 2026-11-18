# AULA S75 Pro

This target is in development. The desktop app identifies the stock USB product as `AULA-S75Pro` at `0c45:800a`. The official driver specifies a 135 × 240 portrait panel and supplies the layout metadata in `layout.json`. That layout describes software key coordinates. The MCU GPIO mapping is recorded separately in `matrix-evidence.json`.

The factory V1.10 image for S1-2808 has SHA-256 `bcc5f633d21f6219b9eebfec2c00b76a4f6bc3246babbe2e157478b26398d598`, a 262144-byte application and checksum `d100`. The update package embeds an SN32F290 family image. These facts establish the research input. The exact installed MCU package and PCB revision remain unverified.

The stock driver was downloaded from the [AULA software page](https://www.aulagaming.com/pages/download). Its S75 Pro installer SHA-256 is `b097008ff9aa4497ca36660e5c61574aca2847500c4263637d236cd92220686b`. The [OEM download page](https://mykeeb.com/downloads/) supplies the S1-2808 V1.10 updater. Vendor executables were extracted as data and were never run. Vendor firmware and executables are excluded from source distribution.

## Simulator

The desktop Firmware and simulator page runs the shared C controls, companion animation and display renderer at the panel's native size. The portrait menu uses the available height with native glyphs. Home keeps its status at the top, centers the companion and clock scene, and anchors the footer to the bottom. The F75 Max retains its 128 × 128 renderer.

The separate bounded routine emulator runs extracted ARM instructions and records GPIO writes, sense inputs, panel initialization commands and orientation offsets. The recovered orientation-zero offsets are 52 columns and 40 rows. Supply the exact factory image to run it.

```sh
.venv/bin/python scripts/emulate_s75.py /path/to/application.bin --output analysis/s75-matrix.json
```

The matrix test stubs GPIO initialization, drive selection during sense testing, and the settle delay. The panel test captures command/data calls while stubbing SPI initialization and timing. It does not execute a complete S75 boot or radio controller. Display simulation does not establish panel initialization, orientation, offsets, SPI timing, or working hardware.

## USB installer

The desktop button loads a bundled release from `firmware/releases/s75pro/`. Release admission checks the target, exact file hashes, image size, validity marker, protected recovery, linked adapter tests and complete ARM system checks. An explicitly optional captured-ROM test may remain unrun. The original private developer flash command retains its stricter captured-ROM requirement.

A release contains `release.json`, `firmware.bin`, `firmware.elf`, `build.json`, `adapter-tests.json` and `system-tests.json`. The release manifest names target `s75pro`, qualification `passed`, SHA-256 hashes for those five payload and receipt files, and the supported original firmware checksums as integer `stock_checksums`. Build metadata names target `s75pro` and display `{"width":135,"height":240}`. Release qualification is a maintainer decision backed by the board's validation evidence.

The installer checks the stock USB product name, requires one USB target, identifies its ROM, checks the installed checksum before erasing, runs the existing verified programming protocol, verifies the programmed checksum, and requests a restart. It writes a private installation receipt and reports failures that need ROM recovery. First installation uses the default custom settings described in the app. Updates from existing custom firmware are outside this initial stock-install path and are rejected by its version check.

No S75 custom firmware release is bundled yet. The app keeps installation unavailable while the board port is incomplete. Remaining work includes full matrix/key mapping, RGB and side-light wiring, selector and encoder behavior, translating the recovered display setup into a live board adapter, radio/battery wiring, a compiled S75 target, full-system emulation, and physical USB recovery plus wake checks. An S75 Pro is needed for the final hardware checks.
