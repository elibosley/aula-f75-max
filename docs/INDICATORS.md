# Connection, charging, and key indicators

This source adds indicators to the Home header and configurable Caps/Fn feedback to key RGB. Building or passing model tests does not install the firmware or confirm physical LED placement and charge-input polarity.

The symbol beside USB, BT1–BT3, or RF shows the selected route's state: a solid mint dot means connected, a hollow crossed dot means disconnected, three dots mean a route change is pending, and two linked dots mean pairing is in progress. A radio command acknowledgment does not count as a host connection. The existing OS icon remains beside these symbols. Menus retain their full-screen headers.

A lightning bolt beside the battery percentage means the debounced charging input is active. A plug means USB is configured while that charging input is inactive or not yet known. The plug does not assert that charging is complete. An unavailable battery gauge still shows `--%`; the charging input is independent of percentage.

The charging input follows the preserved supplier application (`a7d45875…`): routine `0x2184` reads active-low B17 into the flag at `0x20000059`. The stock Home painter at `0xfd8c` uses that flag to select display command `0x0e`, which draws the lightning-bolt battery bitmap from external asset offset `0xbd10`. The new driver only reads B17 and waits 50 ms for a stable level. It does not reconfigure the pin, change charger settings, or infer charging from battery percentage.

Under **Studio → Lighting → Lock and Fn lights**, choose the Caps Lock and Fn-held colors or disable either indication. Caps Lock follows the active host's LED output, not a physical key press. This supports the permanent Caps/Control/Command remapping. USB LED updates cannot alter the active Bluetooth host's indicator. A radio disconnect or route change clears the old radio lock state.

The physical Caps key is key-matrix position 3, RGB position 45. While Caps Lock is on, its color overrides the normal palette. Holding Fn overrides Caps and the physical Fn key (matrix 71, RGB 86) with the Fn-held color. Releasing Fn restores Caps feedback or the current lighting layer. These overlays use the completed RGB buffer and obey brightness and sleep limits; they do not change PWM timing or the LED row interrupt.

The optional custom-record version 3 extension uses bytes 2516–2522 for the two enable bits and RGB colors. Existing version 1/2 records retain their settings and receive default mint/lilac indicator colors in RAM. An unchanged legacy document still encodes byte-for-byte. Editing indicator settings writes version 3 only on an explicit Save. Studio disables these controls until the keyboard advertises support: USB host-status flag bit 2 or Bluetooth capability command 6. The existing Bluetooth protocol-3 Info response and Constant-padding reply carrier are unchanged. No Caps or Fn indicator operation emits a key press.
