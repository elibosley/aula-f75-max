# F75 Studio desktop app

Download the archive for your platform from a successful [Desktop builds run](https://github.com/elibosley/aula-f75-max/actions/workflows/desktop.yml). Extract the complete archive. Open **F75 Studio.app** on Apple Silicon macOS, **F75 Studio.exe** inside the extracted folder on Windows x64, or the **F75 Studio** executable inside the extracted folder on Linux x64. The builds are development packages. Windows uses the system [WebView2 runtime](https://developer.microsoft.com/microsoft-edge/webview2/). Linux uses Qt 6 on an active desktop session.

Connect the AULA F75 Max by USB. Studio reads the current settings when it opens. Choose **Apply** to try a change in RAM. Choose **Save to keyboard** to keep it across restarts. You can configure per-key actions and colors, macros, saved device names and layouts, lighting, companions, wheel action, and power settings. Studio uses the USB settings interface provided by the community firmware.

On Linux, if your desktop user cannot open the keyboard, install the included `70-f75-studio.rules` in `/etc/udev/rules.d/`, reload udev rules, and reconnect the cable. The rule targets USB ID `feed:f750` and grants access to the active desktop user.

## Show computer status

With firmware that supports computer status, select the USB route on the keyboard. In Studio, open **Screen → Computer status**, enter up to 20 printable ASCII characters, and choose **Show on keyboard**. The message appears in the Home footer when the screen is awake. Timers and keyboard notices have priority. A message expires after its selected duration, clears on USB suspend or route changes, and lives in RAM.

Scripts can use the same channel. For example, a build script can run the following command after its tests finish.

```sh
python scripts/host_display.py set 'Build passed' --seconds 20
```

Use `info` to check availability and `clear` to remove the current status. Run the CLI in the desktop environment or the existing firmware tools environment.

The 32-byte USB report starts with `F75y` and a four-byte nonce. Bytes 8–11 hold protocol version `1`, operation (`0` info, `1` set, `2` clear), duration in seconds (`1`–`60` for set), and text length. Bytes 12–31 contain the ASCII text padded with zeros. Info and clear have zero duration, length, and text. The `F75a` reply echoes the nonce and returns version, result (`0` accepted, `1` invalid, `2` USB route unavailable), readiness, and active message state in bytes 8–11. Bit 4 of byte 24 in the existing `F75!` health reply advertises support.

## Build locally

Create a separate Python environment and install `requirements-desktop.txt`. Run `python scripts/build_desktop.py` from that environment on the target operating system. The output is under `dist/desktop/`. The [pywebview installation guide](https://pywebview.flowrl.com/guide/installation.html) lists desktop runtime prerequisites. For source development, run `python scripts/build_preview.py` and `python scripts/desktop.py` in the same environment. Use `--check` to verify the bundled assets and editor API, or `--check-keyboard` to read a connected keyboard through the desktop API.
