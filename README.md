# F75 Studio

Custom firmware and a Mac-friendly editor for the AULA F75 Max. The board gets a chibi desk companion, a little analog clock, clear menus, customizable lighting, macros, per-device layouts, and Bluetooth device switching.

This is an experimental community board port. The physical selector remains authoritative when moved. The keyboard uses its existing radio controller and saved bonds; one device receives keyboard input at a time.

## Make it yours

- Choose from 24 lighting and screen accent presets, use an exact RGB hex color, or paint individual keys and layers.
- Pick a screen accent and light or dark appearance. Text contrast adjusts with the theme.
- Save names and Mac, Windows, Android, or Auto layouts for each connection.
- Switch Bluetooth slots with **Fn+1/2/3**. On Home, **Fn+wheel click** returns to the previous Bluetooth slot. The shortcut uses the last two selected slots during the current session.
- Use **Fn+4** for the receiver and **Fn+5** for USB when those transports are available. Moving the physical selector takes priority; software cannot override a hardware power cut.
- Pair deliberately with **Fn+P**, then hold the wheel for 1.2 seconds. Switching devices does not replace a bond.
- On Mac, physical Caps sends Command when the Caps/left Ctrl swap is enabled. Physical left Ctrl sends Caps Lock. Windows and Android use Ctrl at physical Caps.
- Run a Pomodoro timer, choose the wheel action, and save settings to the keyboard.

[Controls and recovery](firmware/README.md) · [Board target](firmware/targets/f75max/README.md) · [Hardware qualification](docs/HARDWARE_STATUS.md)

## Build

The supported build host is Apple Silicon macOS. Firmware uses SHA-pinned SonixQMK, ChibiOS, and xPack ARM GCC. The build does not require a vendor executable or a factory ROM dump.

```sh
brew install make ninja pkg-config glib hidapi libusb
python3.14 -m venv .venv
.venv/bin/python -m pip install --require-hashes -r requirements-build.lock
make test
make bootstrap
make verify
```

`make verify` builds the USB-only and full-UI profiles twice, compares BIN and ELF hashes, and runs the linked ARM checks. The public checks use modeled electronics and explicitly injected radio events. Captured factory-ROM replay and historical binary regressions are separate private-input checks under `make verify-private`.

[GitHub Actions](https://github.com/elibosley/aula-f75-max/actions/workflows/firmware.yml) publishes firmware, ELF files, SHA-256 checksums, and verification receipts for each successful build. These artifacts contain erased settings regions, not anyone’s device backup or pairing identities.

## Editor and preview

```sh
make preview
```

Open <http://127.0.0.1:8787/hardware.html> for the real keyboard editor, or <http://127.0.0.1:8787/> for the native C preview. **Apply** changes RAM. **Save to keyboard** writes flash and reads the settings back. Connect USB for the editor, even when typing over Bluetooth.

To reach the editor from a phone on your own tailnet, run `serve_native.py` with your Mac’s Tailscale address as `--bind` and port 8787. The service checks origin and a session token. The ARM emulator on port 8788 runs the actual linked image against modeled peripherals and has no flashing endpoint.

## Before flashing

Use the [guarded programming procedure](firmware/targets/f75max/README.md#settings-preserving-programming). It requires an exact source image, a fresh settings capture, verified recovery, and matched checksums. Public CI does not qualify your individual PCB, battery wiring, or recovery method. Factory BOOT/GND recovery has been exercised on the development board; a cold wheel-held reconnect remains a separate hardware check.

[Live Bluetooth switching investigation](docs/BLUETOOTH_MULTIPOINT.md) tracks the requested two/three simultaneous links.

The radio firmware stays on the radio controller. This project does not provide simultaneous Bluetooth links, a new radio stack, or automatic Android identification. Auto layout uses supported USB evidence or an explicitly enrolled host helper; a manual layout remains available.

## License

Source is GPL-2.0-or-later. Inter is under the SIL Open Font License. The Apple mark comes from Bootstrap Icons under MIT; trademarks remain with their owners. See [third-party notices](THIRD_PARTY_NOTICES.md). No vendor updater, factory ROM capture, device backup, host binding, or private network address is included.
