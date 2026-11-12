# Animation and transfer efficiency

The animation candidate adds a small visiting cat to the four existing desk companions. Its sixteen generated poses cover walking, sitting with a blink, and waving. It enters, spends a moment beside the companion, and leaves, with randomized cooldowns. Menus, timers and notification signs retain priority. Reduced motion hides the visitor. The visitor never wakes the screen or writes settings.

The combined update also [remembers the last successful Bluetooth device](BLUETOOTH_LAST_DEVICE.md) independently of normal Save, while retaining physical-selector precedence.

The generated source, exact prompt and native palette manifest are under `assets/characters/visiting-cat/`. `scripts/build_visitor_assets.py` packs the source into a 20×20 sprite with seven opaque colors and transparency. The native preview and keyboard renderer use the generated header. The gallery uses the matching native atlas.

The renderer retains its 4,800-byte sprite cache. It copies aligned four-pixel LZ groups directly and unpacks four palette indices together. A conservative dirty-tile mask skips unchanged companion-screen regions. Other pages, appearance changes and unclassified changes still repaint completely. Pixel tests require every changed pixel to belong to a dirty tile. Page transitions and wake-up still invalidate every tile. SPI timing, RGB interrupts and recovery code are unchanged.

With USB configured, the animation scheduling budgets are 24 FPS in Balanced, 18 in Endurance and 30 in Desk. Battery budgets remain 12, 8 and 20. These are scheduling limits, not measured physical frame rates. Reduced motion, idle dimming and low-battery limits remain in effect.

Offline comparison against installed image `82c8a548…` found identical rendered character pixels and an 8.3–9.2% reduction in Cortex-M0 instructions for full frames. A linked-system test also found zero rendered tiles during one second of an unchanged sleeping pose. Physical frame-rate acceptance requires installation and observation.

## Bluetooth settings

Apply and Save already upload only changed windows. Previously Studio downloaded all 3,232 bytes again afterward. The new host path verifies the live snapshot CRC through Begin/End instead. The CRC excludes embedded record CRC words, whose residue alone cannot identify a snapshot. Both records must remain valid, stale editor baselines are rejected, and an uncertain commit is never retried. Persistent Save still commits a complete validated record for restart integrity.

A reversible test on the installed firmware applied a temporary wheel mode and verified it over Bluetooth in 28.35 seconds, then restored the original in 28.12 seconds. USB readback confirmed byte-for-byte restoration and unchanged Save counters. This measures the candidate host path; the existing desktop app had taken 100 seconds for a full read alone.

The firmware candidate advertises compressed reads with capability bit 2. Command 8 accepts a decoded offset and remaining count within the frozen settings snapshot. Each reply contains a consumed-length u16 followed by bounded tokens. A token's low seven bits plus one give a length. Its high bit repeats the next byte; otherwise that many literal bytes follow. Replies remain at most 256 payload bytes, decoded windows must make progress, and the complete decoded records and snapshot CRC are checked.

Clients use compressed reads only when that capability is explicitly present. Older firmware retains its existing raw-read contract. Corruption, timeout, permission failure or identity changes never trigger another transport or a raw-read retry. The Info v3 response, HID descriptors, Constant-padding report byte and radio firmware are unchanged. Update Studio before installing the new capability so older builds do not reject it.
