# F75 Max board target

This ARM target uses pinned SonixQMK and ChibiOS. Its custom UI runs on the development keyboard. [Hardware qualification](../../../docs/HARDWARE_STATUS.md) separates physical observations from modeled checks. Build receipts and private deployment records are generated locally under the ignored `analysis/` directory.

The factory ROM identifies SN32F29x family 32, chip 5, code options `ffff` and security `5a5a`. The build selects `SN32F299F` with 256 KiB flash and 32 KiB RAM. The recovered application and measured board inputs establish the wiring; the build name alone does not identify the package.

## Adapters and controls

The target includes USB HID, a 15×6 matrix scanner, the real matrix wheel switch, direct SPI display, shared key/RGB scanning, UART2 radio transport, read-only battery gauge, reserved-flash settings, bounded macro playback and fixed configuration/host-evidence protocols. See [the interface guide](../../README.md) for controls, layer behavior, OS detection and limits.

USB identifies as local development device `feed:f750`, F75 Max WIRED TEST. Bluetooth uses the supplier radio and existing bonds. New BT2 pairing and reconnection were observed on the development board. Receiver operation, power rails, battery endurance and cold wheel-held recovery still need physical qualification.

## Build

Run from the project root, using the pinned dependencies in `dependencies.json` and `requirements-build.lock`:

```sh
.venv/bin/python scripts/bootstrap_keyboard.py
.venv/bin/python scripts/build_keyboard.py --clean --output-dir analysis/check/a
.venv/bin/python scripts/build_keyboard.py --clean --output-dir analysis/check/b
```

The build produces BIN, ELF, map and a JSON receipt with complete source/dependency hashes, vector checks, protected recovery hash and symbol-derived RAM reservations. Standard `size` BSS includes unused ChibiOS heap; use the receipt to distinguish globals, stacks and free heap. Runtime stack high-water is not measured.

Never build two targets concurrently: QMK objects are shared and the builder enforces a lock. Native preview, linked ARM, model and physical evidence are separate.

## Verification and admission

Run `test_keyboard_image.py` with `F75_IMAGE` and `F75_TEST_RECEIPT` pointing at the exact candidate. It executes compiled adapters in Unicorn with hardware boundary stubs. Run `test_system_emulator.py IMAGE --output RECEIPT` for reset-through-main execution with real ChibiOS/NVIC/USB/matrix/SPI machine code and no function stubs.

Focused linked-image checks include `test_settings_system.py`, `test_os_system.py`, `test_host_os_system.py`, `test_radio_system.py`, `test_pairing_system.py`, `test_menu_system.py`, `test_custom_system.py`, `test_battery_image.py`, `test_power_scroll.py` and `test_idle_power.py`. Each accepts `IMAGE --output RECEIPT.json`. The idle test reaches ChibiOS's actual WFI idle thread, resumes through interrupts, and delivers 24 short USB key pulses across idle scan phases. The radio test also checks the first key after idle without USB enumeration. The pairing test rejects stale link status before command transmission and requires more than a command acknowledgment to finish pairing. Radio replies are explicitly injected; these do not emulate an RF host, receiver, battery electronics or analog power rails.

`admit_candidate.py A B --check ...` requires two identical clean BIN/ELF builds, matching current sources, full-system checks and each named receipt. It stages and atomically archives the exact artifacts and board source. Programming is a separate explicit action. The archive's canonical image contains erased settings regions.

## Settings-preserving programming

Capture fresh records from the running application using its archived source image hash:

```sh
.venv/bin/python scripts/keyboard_settings.py --capture analysis/before-update.json --source-sha CURRENT_BASE_SHA
```

The capture includes legacy and expanded records, generation/counters, and a reconstructed live checksum. It rejects changes during capture. Keep the exact archived source image. A previous base checksum is not the current checksum after Save.

Request the retained software ROM path with `keyboard_health.py --boot`. Its acknowledgment does not prove USB re-enumeration has completed. Verify the observed factory ROM and its identity/checksum before programming; a short disappearance during transition does not justify replaying an erase/program operation.

Use only `flash_keyboard.py` with the admitted candidate hash, exact captured current checksum, and `--settings-backup`. It validates family/chip/protection, merges only the fixed reserved regions, verifies erase/program/checksum and requests application return. The receipt records both the canonical base identity and actual merged payload hash. It implements no security downgrade. The native flasher's default security-changing path is not a diagnostic probe.

The old supplier download is preserved for factory restoration. It is not a readback from this keyboard. A matching 16-bit checksum alone does not prove byte-for-byte identity.

## Recovery invariants

`recovery.S` owns the protected reset range. It isolates C9 drive and B14 sense, matrix row 14/column 0, active high, before C initialization, HAL, clocks, scheduler, USB and display. P1.17 is not this board's wheel button. Preserve the reset scan, factory ROM handoff, explicit return marker, raw software boot request and exception path. Exact recovery hash and captured-ROM checks are admission requirements. Physical factory BOOT/GND recovery is established; physical cold wheel-held entry remains pending.

The ChibiOS clock patch masks `AHBCP_b.AHBPRE`, rather than switching on the entire register including DIV1P5. All 16 divider states execute in the model. This reproduced an early startup fault; it does not establish the original physical handoff value.

## Display/RGB invariants

The accepted display path uses 8-bit SPI at 8 MHz, CS per byte and completion checks for RX plus BUSY clear. Only the shared CT16B3 scan IRQ is deferred while a byte is selected, including bounded timeout cleanup. USB, radio and system timers remain enabled. Restoring the prior IRQ state is required. Removing that guard reproduced corruption even with LEDs dark.

CT16B1 match/control fields are unkeyed. CT16B0/2 require the Sonix key. Writing the key into CT16B1 enabled unintended reset/interrupt bits and caused flicker. Keep the hardware PWM stop thresholds and timer4 RTOS timebase. Render complete back buffers outside the IRQ and publish at color-frame boundaries.

At idle-off, CT16B3 continues matrix scanning with MR0=511 rather than 255, while CT16B0/1/2 remain stopped with their PWM mux detached. Preserve the prior CT16B3 interrupt enable state when changing period. Raw matrix activity restores the active period; diagnostic suspension must remain suspended. Skip redundant dark color frames. The main task's 1 ms wait allows the existing ChibiOS WFI thread to run while peripheral interrupts remain enabled. This does not implement deep Stop mode or radio sleep.

The display retains the stock offsets and RGB565 byte order, with 2048-byte tiles and no full framebuffer. Page transitions invalidate all tile signatures. Idle wake redraws a fresh frame before enabling the backlight. Physical menu motion and steady lighting have prior user acceptance; later images still require their own regression evidence.

## Source distribution

The combined image uses GPL-licensed QMK code. Retain pinned upstream sources/licenses, board port, shared C modules, generated assets and Inter's SIL Open Font License with any distribution.
