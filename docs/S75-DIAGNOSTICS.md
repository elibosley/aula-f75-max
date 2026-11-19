# Share S75 Pro diagnostics

S75 Pro firmware is experimental. Source builds and emulation pass, but physical
recovery, screen wiring, radio and charging behavior have not been validated.
Normal installation stays disabled until those checks pass on real hardware.

1. Download the desktop application for your operating system from GitHub Releases.
2. Connect one S75 Pro using a USB data cable and select its wired mode.
3. Open **Keyboard → Install Custom Firmware**, then **Share S75 diagnostics**.
4. Select **Collect USB diagnostics** and review the report. It contains the app
   version, operating system family and allowlisted USB descriptor fields. It
   excludes serial numbers, HID paths, key input, settings and firmware dumps.
5. Select **Open GitHub issue draft**. Sign in to GitHub, add your keyboard
   revision/product link and observations, then submit the issue. Issues are
   public; nothing is submitted by the app automatically.

Collection only enumerates USB descriptors. It does not open the keyboard,
enter recovery or change firmware. If detection fails, use a different data cable
and USB port, select wired mode, then collect again. The failed-detection report
can also be shared through the issue draft.

## Hardware acceptance still needed

An initial descriptor report helps identify the device; it does not prove that a
firmware image is safe for that board. Before opening installer admission, the
release owner must validate the exact board/revision and stock firmware, recovery
entry and successful return, USB typing, matrix and wheel, screen dimensions and
colors, settings persistence, Bluetooth pairing and wake, selector routing, and
charging/unplug indicators. Preserve settings and recovery evidence for each
candidate. Use a coordinated validation session before attempting custom firmware.
