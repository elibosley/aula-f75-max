# ARM system emulator and reproducible builds

This emulator runs the linked keyboard image from its real reset vector. QEMU
provides the Cortex-M0 CPU, exception entry/return, NVIC, SysTick, and ChibiOS
context switching. The board model supplies clock registers, GPIO/matrix inputs,
the free-running timer, USB endpoint memory and bus events, and SPI completion
interrupts. Firmware functions are not replaced with host callbacks.

The captured factory ROM is exercised in the recovery tests, including its USB
enumeration and explicit application return. Its chip-ID metadata is inferred.
These checks do not prove physical cold wheel recovery. GPIO polarity,
oscillator readiness, USB PHY behavior, panel electronics, RF pairing, and
battery current need hardware tests. Execution time is instruction based, not
cycle accurate. UART replies and gauge values are injected explicitly in the
focused tests; no RF host or battery electronics are simulated.

## Reproduce

The verified host is Apple Silicon macOS, Python 3.14.6, Apple Clang 21, GNU Make,
Ninja, pkg-config, and GLib 2.88.2. Firmware uses the hash-pinned xPack ARM GCC
15.2.1 toolchain, not the host compiler. The current bootstrap supplies the
Darwin ARM64 toolchain; another host needs an explicitly pinned toolchain for
that platform.

From the project root:

```sh
python3.14 -m venv .venv
.venv/bin/pip install --require-hashes -r requirements-build.lock
make bootstrap
make verify
```

`make verify` validates every archive-owned dependency file, allowing only the
recorded clock, SPI-completion and timer4 patches. It clean-builds USB-only and full-screen profiles
twice, compares the binary and ELF hashes, records compiler input hashes, and
runs both adapter tests and complete ARM system tests. The full-screen profile
also runs settings, USB OS detection, host evidence, radio, pairing status,
menu redraw, customization, battery, power/scroll, idle/wake and failed-switch checks against
that exact image. The research/protocol suite also runs. Each attempt has its own directory under `analysis/repro/runs`;
`analysis/repro/latest.json` points to its receipt, including failures. This
proves clean-build repeatability on the recorded host and source path. It does
not claim an independently reproduced build on another computer.

Verification does not change the installed image or its default emulator
pointer. The reproduction receipt's `emulator_image` field names its separate,
uninstalled full-screen artifact. Pass that path explicitly to
`serve_emulator.py` to inspect it.

Public builds use the source assets and checked-in board map. Supplier images, factory ROM captures and archived failed images are private inputs for `make verify-private`; they are not needed by public CI. QEMU 10.1.3 comes from the official release archive and
is SHA-256 pinned. Its pinned DTC subproject is fetched by QEMU's build system.
The model source and emulator binary hashes are recorded separately.

QMK's supported `SKIP_VERSION` mode removes wall-clock and Git metadata. Builds
also use a fixed epoch, UTC locale settings, and compiler path normalization.
Build receipts retain a real observation timestamp outside the firmware image.
The link map and receipts can contain host paths; binary and ELF files are the
compared artifacts.

## Tests and evidence

The system suite checks:

- Every valid AHB prescaler handoff value reaches `main`.
- The archived failed image faults before `main` with DIV1P5 enabled.
- The archived SPI driver produces excess transfer bytes; the fixed image's
  initialization and pixel transfer lengths match the recovered display protocol.
- All wheel/software-magic reset combinations reach C startup or the ROM boundary
  with dirty RAM, without using the C stack before recovery.
- USB reset, descriptors for all HID interfaces, address assignment,
  configuration, keyboard reports, and raw HID health replies use the real ISR.
- Caps/physical Ctrl and Mac Command mapping reach USB reports, followed by releases.
- Matrix scans and display frames advance through the real firmware loop.
- Wheel quadrature produces two-detent menu selection, and a held wheel returns home.
- Fn+M changes the OS profile; Caps/Ctrl remains swapped under Windows USB reports.
- A missing SPI completion triggers the startup watchdog and reaches the ROM
  boundary. A missing PLL-ready signal is identified as a pre-main stall; early
  wheel recovery remains independent of that signal in the model.

A passed full-screen run includes a PNG decoded from actual SPI writes. The
model rejects unexplained MMIO access in the tested path. Reserved bits and
unimplemented behavior within documented register banks are not silicon
validation. The earlier Unicorn tests remain useful for narrow adapter tests;
they are not the full-system evidence.

## Interactive emulator

The running tailnet service is available at `http://127.0.0.1:8788/`.
The Mac must stay awake and connected to Tailscale.

```sh
.venv/bin/python scripts/serve_emulator.py /absolute/path/to/f75max-wired-test.bin
```

Open `http://127.0.0.1:8788/`. Add `--bind <tailscale-ip>` to reach it over the
same tailnet. The browser sends virtual wheel and matrix inputs. Screen pixels
come from the ARM image's SPI writes, and key reports stay in the virtual USB
host. The CPU pauses between requests; the animation control advances virtual
time while the page is open. This service has no flashing endpoint.

The native-C interface design preview on port 8787 remains a separate service.

The exact installed diagnostic can be tested separately with
`.venv/bin/python scripts/test_installed_diagnostic.py`. Its receipt distinguishes
a modeled clock-state fault from a proven cause on the physical board.
