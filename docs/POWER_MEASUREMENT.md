# Power measurement and deeper sleep

The first step is a measured baseline on the current firmware. Optimizing power
before that baseline would make it harder to identify which change helped.
No current-draw, runtime multiplier, or full-charge endurance result exists yet.

## Battery-only telemetry

The optional read-only power RPC returns the cached gauge estimate, raw SOC,
voltage, charge-input state, USB enumeration, power-policy stage, MCU uptime,
gauge-sample uptime, configuration fingerprint, and matrix activity count.
It reads no typed text or key codes and does not apply settings, save flash,
resample the gauge, or wake the display. Its response uses the already qualified
Bluetooth Constant-padding carrier. Wired `F75b` diagnostics return the same
24-byte payload, but wired samples cannot count as discharge measurements.

Bluetooth command 11 has no settings session, offset, count, or body. It rejects
active settings transfers. Existing Info, capabilities, and fast settings
formats remain unchanged. Payload version 1 is `<BBBBHHIIII`: version, flags,
percent, policy stage, millivolts, raw SOC, uptime, gauge timestamp,
core-configuration CRC32, and activity epoch. Flags are gauge-valid, charge-known,
charging, USB-configured, and radio-connected, from bit 0 to bit 4.

USB-configured requires both the configured driver state and an advancing
host SOF frame counter within the last 100 ms. On this self-powered board, the
driver can retain `USB_ACTIVE` after cable removal. That cached state must not
drive the USB-power icon, battery power limits, or discharge admission. The
existing SN32 `USB_FRMNO` register supplies the evidence without enabling an
extra interrupt; the charging input remains separate.

This is live USB data-link evidence, not a mapped VBUS sensor. A charge-only
cable or a suspended computer with a full, non-charging battery cannot be
excluded by those two software observations alone. The cable must physically
remain unplugged throughout a battery-only trial.

`scripts/battery_benchmark.py --sample` reads one sample. `--record` runs for a
finite duration, with a minimum five-minute interval and a 5% reserve cutoff.
Use the existing enrolled Mac probe and exact board identity. A persistent
service manager must own a long run; an interactive shell is not the waiter.
The output is private, exclusively created JSONL. Existing runs are never
overwritten. Recording requires explicit confirmation that the cable is out.

A discharge result rejects live USB traffic, an active or unknown charging input,
stale gauge data, core-configuration changes, MCU resets, host sleep gaps, and clock
discontinuities. A Bluetooth disconnect is an observation failure, not proof
that the battery is empty. A time-limited interval or the 5% reserve cutoff is
not reported as a full-charge-to-shutdown measurement. The firmware identity
in the log is supplied from the verified installation record, not attested by
the device. A gauge SOC difference is not a current or energy measurement.

The CRC covers the core configuration. It does not cover custom per-key colors,
custom screen colors, bindings, or macros. Keep those unchanged too; this
telemetry cannot automatically detect edits to the custom configuration. Retain
the initial complete settings snapshot with the private test records and check
it again at the end. A change invalidates a claim of matched test conditions.

Polling itself consumes some power. Keep the same interval in repeat trials
and establish its effect with a separate trial before making a precise runtime
claim. If the Mac sleeps, the run cannot silently treat that gap as continuous
sampling. Mac Input Monitoring must already be granted to the enrolled probe;
the logger does not request new access or change macOS power settings.

## Comparison procedure

1. Finish the unplugged charging-indicator check. Charge the battery fully and
   confirm the charging input is inactive, rather than assuming `100%` means
   charge completion.
2. Record the exact firmware image, battery starting voltage and raw SOC,
   Bluetooth host, room conditions, power profile, lighting color/brightness,
   screen face/brightness/motion, idle timings, and intended activity pattern.
3. Run the custom firmware on battery only. Keep the configuration fixed.
   Record active, dimmed, and dark idle intervals separately. The first
   24-hour observation answers a daily-use question; it is not a controlled
   comparison with the supplier firmware.
4. Repeat from the same starting conditions with the supplier firmware, then
   repeat the custom trial. Preserve and restore custom settings around stock
   installation. Never write the radio firmware or reset pairing identities.
   Supplier firmware cannot be assumed to implement the custom telemetry RPC;
   use its supported display/gauge observations or an independent instrument.
5. Report the observed interval and endpoint directly. Only compare matched
   workloads and endpoints. A short, quantized SOC slope cannot establish a
   full-charge runtime or an efficiency multiplier.

Current-meter measurements are deferred at the user's request. A USB meter
measures input power including any charging; it does not directly measure
battery current. An inline battery measurement needs the correct physical
instrument and connection. Neither is inferred from the software gauge.

## MCU sleep investigation

The [Sonix SN32F290 manual, version 1.8, sections 4.3–4.7](https://www.sonix.com.tw/webapi/fl219871/SN32F297_V1.8_EN.pdf)
covers this MCU family. `PMU_CTRL` at `0x40032040` selects normal (`0`), sleep
(`4`), or deep sleep (`2`) before WFI. Ordinary sleep retains peripheral
interrupt wake. Deep sleep stops the high-speed peripheral clocks; the manual
lists GPIO, RTC, LCD, and reset as wake sources. A UART or the current matrix
scan timer cannot be assumed to wake deep sleep.

The captured supplier application explicitly writes `2` before WFI at
`0x0290` and `0x08c0`, then restores clocks, scan configuration, and radio
state. Its shallow-sleep path writes `4` at `0x1126`. These are useful software
oracles, not proof that a copied sequence will work with the custom scheduler.
The pinned SonixQMK `SN_SN32F290/configs/chconf.h` already selects ordinary
MCU Sleep: its idle-enter hook writes `4` to `SN_PMU->CTRL`, and its idle-leave
hook restores `0`. These hooks are linked into the current firmware. The
linked-image idle test now checks both register values around the real WFI
and interrupt wake path. Earlier documentation overlooked these inherited
hooks; ordinary MCU Sleep is already implemented. Its current savings have
not been measured. Deep sleep and radio sleep remain separate work.

Before enabling deep sleep, establish and test:

- Matrix wake: the 15 shared drive rows must expose all six sense inputs,
  including Fn and the actual wheel switch at row 14 / column 0. PWM ownership
  and GPIO direction must be restored without a phantom press.
- Wheel and selector wake: both encoder phases and both selector contacts need
  usable edge interrupts. A held key or already-active wake input must prevent
  entry, and input arriving during entry must not be lost.
- Radio wake: UART RX needs an independent GPIO wake path and a proven
  handshake. Waking on the first UART edge can lose the first packet; do not
  infer that a baud-rate UART will survive a stopped clock.
- Cable wake: the charging input is not equivalent to VBUS presence. A full
  battery may have an inactive charging input while connected. USB attachment
  needs its own verified wake signal.
- Timekeeping: stopped timer 4 and the RTOS tick need an RTC-based elapsed-time
  correction. The focus timer, clock, debounce, radio timeouts, and bounded
  macro playback must remain correct across sleep and timer wrap.
- Recovery: pending saves, uploads, held usages, queued reports, pairing, and
  recovery entry must prevent sleep. Verify byte-exact protected recovery and
  first-key delivery after physical wake.

Radio sleep is separate. The qualification section below documents the recovered
supplier-controller idle command and wake handshake. Do not send guessed
commands or change radio firmware to make a power-saving claim. Keep speculative
MCU or radio sleep out of the daily-use image until its wake and recovery paths
have passed both linked-image tests and physical trials.

## Radio idle qualification candidate

`build_keyboard.py --radio-sleep-qualification` enables a separate experimental
image. Normal builds leave this behavior disabled. The stock application sets
its BT idle command to `0x55` at `0x204`; executing its actual TX dispatcher at
`0x45e4` with that state produces `A6 55 FB`. The linked-image regression also
executes this stock packager, rather than trusting a copied packet constant.

The candidate requests that command only on the selected Bluetooth route after
the configured Sleep timeout, with no held matrix key, macro, mouse button,
pairing, settings transfer, save, boot request, or pending display frame. The
radio queue must be empty, with no partial RX or pending acknowledgment, and
quiet for 100 ms. The sleep command has a 100 ms acknowledgment deadline with
two retries. Reports and slot selection retain their 10 ms deadline. A missing
acknowledgment latches failure instead of repeatedly sending idle requests.

The first new input sends the stock wake preamble `A6 00 A6`, waits 3 ms,
then continues its queued report and key release. The stock dispatcher takes
this path while a key report is pending and its radio-busy flag is set. It
does not arm the normal ACK/retry snapshot for this preamble. The custom
adapter follows that behavior instead of treating slot selection as wake.
Startup also wakes the retained radio before sending its selected-slot command.
This never requests pairing or changes bonds. The preamble is also required
when the idle acknowledgment was lost: an unknown outcome cannot prove that
the controller stayed awake.
Receiver idle behavior is not enabled. Diagnostic radio status bits 4..7 now
show phase 0 (normal), 1 (idle pending), 2 (idle UART-acknowledged), 3 (wake
pending), or 4 (control timeout).

A UART acknowledgment establishes only the transport outcome. Physical testing
must establish continued connection behavior and first-key delivery before
this becomes a default build feature. No radio-current reduction is claimed.
The MCU remains in the existing interrupt-preserving ordinary Sleep mode in
this qualification image. MCU deep sleep additionally needs a retained RTC
timebase, GPIO wake handling, and physical USB/UART wake qualification; those
are not supplied by the radio command alone. Keep the running baseline image
unchanged until that test is intentionally concluded or interrupted.

The new radio control routines occupy the previously unused flash bank starting
at `0x3a000`. The build checks the section's load/run address and upper bound
`0x3e800`, and still requires both customization records, the route journal,
and legacy settings pages to be blank in a canonical image. This preserves
the existing programming backup/restore boundaries and protected recovery.

Executing stock GPIO wake setup at `0xda4` gives interrupt masks `0xc0400`
(A), `0x8c004` (B), and `0x80000` (D). These cover the six matrix sense inputs
and both selector contacts. They do not arm the encoder phases A2/A3, UART RX
B6, or charging input B17. Copying that setup alone would not establish all
of the custom firmware's wake requirements. The USB power input remains
unmapped; the charge input is not a substitute for cable detection.

### Physical idle-command observation and bounded trace

The first cabled BT2 qualification reached the configured Sleep timeout and
sent the idle command three times, then reported the existing UART timeout.
The test restored the original Desk profile without Save and verified the
complete live settings snapshot byte-for-byte. That outcome does not establish
radio sleep or an efficiency gain. The generic-ACK assumption needs hardware
evidence before this feature can become a default build option.

Fixed USB request `F75L` returns exactly 24 bytes: three eight-byte entries
`<IBBBB>` containing parser uptime, three control bytes, and state. Entries
hold the previous RX, latest RX, and last transmitted A6 control. State bits
0..2 carry the qualification phase, bit 3 the pending-ACK state, and bits
4..5 the retry count. Bit 7 in the last TX entry marks the snapshot frozen
before the next wake attempt. A `CLRTRACE` payload clears only this diagnostic
snapshot. No key report is recorded. Encoded LED-padding payloads and unknown
RX payload bytes are masked. Timestamps show parsing/transmission, not measured
RF activity or wire-level arrival timing. The trace uses exactly 24 bytes and
the existing 4096-byte minimum heap reservation remains enforced.

The next physical BT2 trial retained normal `61 0D 0A` replies parsed 12 ms
and 30 ms after the final sleep transmission. Both arrived after the old 10 ms
deadline. The user then confirmed that the first `w` in `wake` appeared
immediately and all four letters arrived. The original Desk profile was
restored without Save; saved settings remained unchanged. This validates that
physical first-key path, but does not measure radio current. A linked-image
regression now checks a 40 ms sleep acknowledgment without retransmission.

The stock wake oracle executes two dispatcher passes: the first keeps the
pending key and sets the wake flag, and the second sends `A6 00 A6`, calls
the 3 ms delay, and reaches RX processing without arming the ACK snapshot.
A separate linked ARM adapter check verifies that the next packet is blocked
at 1 and 2 ms and permitted at 3 ms. These are software checks; physical wake
and radio-current measurements remain separate gates.
