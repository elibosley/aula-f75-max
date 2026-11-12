# Remembering the Bluetooth device

The earlier firmware initialized `last_bt_slot` to BT1 in RAM at every startup. It changed when selecting a device but did not persist that value. A separate startup reset also set the active route to USB before applying the physical selector.

The new source keeps the last successfully connected BT1, BT2 or BT3 in a separate preference journal. Startup uses that slot only when the physical selector is on Bluetooth. USB starts on USB, and the receiver position starts on the receiver. A failed Bluetooth connection does not replace the last successful device. Pairing and saved bonds are unchanged.

The connection must remain valid for one second, and there must be 200 ms without key activity before the preference is committed. An active configuration session or busy radio defers the write. Reconnecting the same device does not write again. The initial implicit BT1 default does not need an extra record. An error is shown as `BT memory failed` and is not retried repeatedly within the same connection.

The journal uses two separate 1 KiB pages at `0x3e800` and `0x3ec00`. Each entry contains a magic value, sequence, slot and CRC. Entries are appended in 16-byte slots. Rollover erases only the page without the newest valid entry. A partial entry fails CRC validation; a complete newer entry wins. This does not Save the normal settings record, so unsaved colors, macros and screen changes remain unsaved.

The builder explicitly reserves both pages. The backup tool reads them only when the firmware advertises route-memory support in health bit 5. A fixed metadata stamp rejects a route change during backup. The guarded flasher preserves existing journal bytes, or seeds the first entry from a confirmed live Bluetooth connection when upgrading earlier firmware. Only candidates declaring the reserved journal may receive it. Factory ROM, reset recovery, settings banks and the image trailer are outside these pages.

Portable tests cover rollover, every interrupted-write prefix, CRC rejection, sequence wrap and duplicate suppression. Linked ARM tests cover a successful BT2 connection, a failed BT3 attempt, cold startup on BT2, and USB/receiver selector precedence. Physical power-cycle acceptance remains a separate installation check.
