# F75 Studio desktop app

Download the archive for your platform from a successful [Desktop builds run](https://github.com/elibosley/aula-f75-max/actions/workflows/desktop.yml). Extract the complete archive. Open **F75 Studio.app** on Apple Silicon macOS, **F75 Studio.exe** inside the extracted folder on Windows x64, or the **F75 Studio** executable inside the extracted folder on Linux x64. The builds are development packages. Windows uses the system [WebView2 runtime](https://developer.microsoft.com/microsoft-edge/webview2/). Linux uses Qt 6 on an active desktop session.

Studio starts in **Automatic** connection mode. It reads the selected USB route, or uses the enrolled Bluetooth keyboard connected to this Mac when the keyboard is on Bluetooth. A diagnostic USB cable can remain attached while Bluetooth is selected. Settings and notifications share this connection. You can also choose USB or Bluetooth explicitly. Studio checks connections between operations and never repeats an interrupted save over another transport. Changes save automatically after a 900 ms pause, including persistence across keyboard restarts. Sliders and text entry are grouped into one save; returning to an unchanged value avoids a write. You can keep editing during a save: newer edits stay visible and go next using the last verified baseline. A failed save keeps the draft and pauses automatic writes until you choose Retry save or Reload. Incomplete macros and invalid fields wait for correction. The header shows waiting, saving, saved, or error state. Reload asks before discarding pending edits. Closing the desktop window warns when changes have not finished saving. You can configure per-key actions and colors, macros, saved device names and layouts, lighting, companions, wheel action, and power settings. Studio uses the USB settings interface provided by the community firmware.

On Linux, if your desktop user cannot open the keyboard, install the included `70-f75-studio.rules` in `/etc/udev/rules.d/`, reload udev rules, and reconnect the cable. The rule targets USB ID `feed:f750` and grants access to the active desktop user.

## Keyboard notifications

In Studio, open **Notifications**, enter up to 20 printable ASCII characters, then choose **Show on keyboard**. Notifications use the same connection as settings. The installed firmware displays messages in the Home footer. The sign-mode firmware candidate makes all four companions hold the notification on a small sign instead. This candidate is not installed yet.

Use notifications for build results, downloads, meeting reminders, music changes, or other app events. The channel accepts text from any integration; Studio does not automatically collect operating-system notifications. Messages appear on an awake Home screen, expire after 1–60 seconds, and live only in RAM. A new message replaces the previous message. Menus, pairing, active timers, and settings transfers keep priority. Messages do not wake a sleeping keyboard. USB messages clear on suspend or route changes; Bluetooth messages clear on disconnection or route changes.

Scripts can use the same channel. For example, a build script can run the following command after its tests finish.

```sh
python scripts/host_display.py notify 'Build passed' --seconds 20
```

For the local macOS Bluetooth, add `--transport bluetooth --probe '/absolute/path/to/F75 Wireless Probe.app/Contents/MacOS/F75WirelessProbe'` before `notify`. Use the enrolled helper executable from the local preview. Bluetooth status sends are output-only: success confirms reports were sent, not that the panel was observed.

Use `info` to check availability and `clear` to remove the current status. Run the CLI in the desktop environment or the existing firmware tools environment.

The 32-byte USB report starts with `F75y` and a four-byte nonce. Bytes 8–11 hold protocol version `1`, operation (`0` info, `1` set, `2` clear), duration in seconds (`1`–`60` for set), and text length. Bytes 12–31 contain the ASCII text padded with zeros. Info and clear have zero duration, length, and text. The `F75a` reply echoes the nonce and returns version, result (`0` accepted, `1` invalid, `2` USB route unavailable), readiness, and active message state in bytes 8–11. Bit 4 of byte 24 in the existing `F75!` health reply advertises support.

## Build locally

Create a separate Python environment and install `requirements-desktop.txt`. Run `python scripts/build_desktop.py` from that environment on the target operating system. The output is under `dist/desktop/`. The [pywebview installation guide](https://pywebview.flowrl.com/guide/installation.html) lists desktop runtime prerequisites. For source development, run `python scripts/build_preview.py` and `python scripts/desktop.py` in the same environment. Use `--check` to verify the bundled assets and editor API, or `--check-keyboard` to read a connected keyboard through the desktop API.

## Local Mac Bluetooth

Run `python scripts/build_desktop.py --with-bluetooth` in the desktop environment. Open `dist/desktop/F75 Studio.app`. This includes the Bluetooth helper in the regular Mac app and uses this checkout's enrolled keyboard identity. Personal enrollment and qualification files stay outside the app archive. Published archives currently include USB support. The older `--local-bluetooth-preview` build flag remains available for a separate development bundle.

Bluetooth Apply and Save upload changed windows and verify the complete live snapshot CRC, without downloading all unchanged settings again. New firmware also advertises compressed initial reads; older supported firmware uses its explicitly negotiated raw format. Both paths validate records and snapshot identity. See [animation and transfer efficiency](ANIMATION_AND_TRANSFER.md) for the measured test and wire contract.

**Automatic** selects Bluetooth when the enrolled keyboard is connected on Bluetooth, even with a diagnostic USB cable attached. The connection menu shows the selected route and slot. Status delivery and challenge replies have been physically verified with USB unplugged. Messages expire after the selected duration and appear only on an awake Home screen, subject to timer and notice priority.

Bluetooth settings require the enrolled keyboard to pass the Constant-padding qualification described in [the Bluetooth investigation](BLUETOOTH_MULTIPOINT.md#settings-candidate). Earlier replies used the Apple Fn field and produced unwanted key events. Those images are retired. The installed candidate passed a 16-pattern zero-key-event sweep, physical full Read, reversible Apply, explicit Save and power-cycle persistence with USB unplugged. The packaged app window needs macOS Input Monitoring permission; its actual native-window Bluetooth Read also loaded the real keyboard settings after permission was granted. Use **Request Input Monitoring** only when you want to grant that access. Enable F75 Studio in **System Settings > Privacy & Security > Input Monitoring**, then quit and reopen it. Checks alone never request permission. Windows and Linux retain USB settings. Radio firmware and Bluetooth bonds are outside this settings channel.

**Screen → Sync clock from this device** uses the selected Automatic, USB, or Bluetooth connection. Bluetooth requires the clock-capable firmware candidate; older firmware keeps the Bluetooth button disabled with an update message. Sync sends local seconds since midnight and requires an exact CRC-checked time echo. It does not begin a settings session or save flash. A failed sync is not retried on USB. The clock continues in RAM and needs syncing after power loss. Bluetooth clock sync has passed linked ARM UART-to-Home and browser/API tests; physical verification and installation are pending. The separate background host helper still synchronizes through USB.

## Transfer progress

Studio displays loading, automatic saving, and verification progress. Byte percentages describe the current transfer step, not the whole operation. Save is complete only after readback verification. An interrupted or failed request retains editor changes and requires reading the keyboard before retrying; Studio never automatically repeats a Save. The sign-mode firmware candidate shows transfer progress on the selected companion’s sign.

## Lock and Fn lights

With indicator firmware installed, **Lighting → Lock and Fn lights** sets separate Caps Lock and Fn-held colors. Caps follows the active computer’s lock state, including remapped keys. Holding Fn temporarily highlights Caps and Fn; release restores the current palette or Caps feedback. Color changes save automatically and remain after restart. Older firmware shows these controls disabled. See [indicator behavior and verification](INDICATORS.md).
