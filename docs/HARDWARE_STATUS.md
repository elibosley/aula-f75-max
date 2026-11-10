# Hardware qualification

The development board is an AULA F75 Max using the recovered SN32F29x target, a 15×6 matrix, a 128×128 RGB565 display, and the supplier radio controller.

Physically observed on the development board: USB typing, Bluetooth typing on two saved slots, reconnection of a new BT2 bond after a main-MCU update, the Caps modifier policy before the latest Command change, wheel navigation, steady RGB output, clear display motion, and the latest icon/text clarity. Software builds and emulator tests remain separate evidence from physical acceptance.

The new screen/color controls and previous-device shortcut require physical checks after installation. Receiver operation, fully wireless host-helper access, Windows/Android hardware layouts, per-key RGB location/order, macro output, battery endurance/current, cold-power Save, and cold wheel-held recovery remain pending. Do not infer these results from a green CI run.

Factory BOOT/GND recovery and settings-preserving programming were exercised on the development board. The reset-entry wheel path is preserved before C initialization. No security downgrade is implemented.
