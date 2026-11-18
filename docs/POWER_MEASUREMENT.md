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
configuration CRC32, and activity epoch. Flags are gauge-valid, charge-known,
charging, USB-configured, and radio-connected, from bit 0 to bit 4.

`scripts/battery_benchmark.py --sample` reads one sample. `--record` runs for a
finite duration, with a minimum five-minute interval and a 5% reserve cutoff.
Use the existing enrolled Mac probe and exact board identity. A persistent
service manager must own a long run; an interactive shell is not the waiter.
The output is private, exclusively created JSONL. Existing runs are never
overwritten. Recording requires explicit confirmation that the cable is out.

A discharge result rejects USB power, an active or unknown charging input,
stale gauge data, configuration changes, MCU resets, host sleep gaps, and clock
discontinuities. A Bluetooth disconnect is an observation failure, not proof
that the battery is empty. A time-limited interval or the 5% reserve cutoff is
not reported as a full-charge-to-shutdown measurement. The firmware identity
in the log is supplied from the verified installation record, not attested by
the device. A gauge SOC difference is not a current or energy measurement.

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
The custom source currently yields to ChibiOS's WFI idle thread but does not
explicitly select a PMU mode. Reaching WFI alone therefore does not establish
the hardware's low-power mode. Measuring and verifying shallow sleep comes
before claiming savings from it.

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

Radio sleep is separate. Its supplier-controller command, acknowledgment,
retention, and wake handshake are not yet mapped. Do not send guessed commands
or change radio firmware to make a power-saving claim. Keep speculative MCU
or radio sleep out of the daily-use image until its wake and recovery paths
have passed both linked-image tests and physical trials.
