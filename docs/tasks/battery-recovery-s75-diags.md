# Battery recovery and S75 diagnostics

Base: 2d6487581a8c99119a6469d09dc067ac4ff6751b.

G1: A finite battery recording survives transient Bluetooth outages and unavailable gauge readings, retains rejected readings and exact validation errors, and reports gaps and device-clock discontinuities without claiming continuous observation or sleep. Firmware/configuration/board/transport changes and external power remain terminal. No old recording is replayed.

Cause: StudioSampler already retries until its deadline. battery_benchmark.record validates a recovered reading before appending it; ValueError escapes to the worker, which retains only the exception class. Device uptime disagreement is currently fatal even in the explicitly gap-tolerant mode. The old run's exact ValueError was not retained, so its precise cause is unknown. Finalization can also fail before publishing a result if partial summarization raises.

G2: A new, physically unplugged, identity-checked 24-hour campaign records actual estimates and complete settings, with immutable receipts. Blocked until the connected F75 is available; the first live check found no USB or enrolled Bluetooth device. Existing recordings remain immutable.

G3: macOS app bundle metadata matches package.json before signing and packaging. Cause: PyInstaller defaults to 0.0.0 and the build never stamps the project version.

G4: An S75 owner can collect and preview a bounded USB-descriptor report and open a GitHub issue draft with that report. Cause: the desktop has installation and simulation bridges but no diagnostic sharing capability. No upload backend or credentials exist. Use GitHub's browser issue form; the owner reviews and submits it. Never include HID paths, serials, key input, settings, firmware dumps, hostnames or usernames. Physical USB/recovery/display/radio qualification remains blocked until a real S75 is available.

Scope: extend the existing recorder, worker, desktop build and firmware-page bridge. Reuse model metadata, HID enumeration and existing controls/cards. No new service, background runtime, auto-flasher or qualification authority. Existing installer admission remains unchanged. UI authority: extension of existing firmware page, colors/tokens/layout unchanged.

Governance queried 2026-11-19 for repository elibosley/aula-f75-max, project f75-studio, workflow battery-diagnostics: no matching Decision or Trust Boundary records. Runtime/source owners are this repository and installed Studio; no organizational authority inferred.

Architecture forecast: NOT_REQUIRED (repository has no mandatory architecture review receipt). Reuse benchmark validation, sampler retries/events, worker receipt finalization, DesktopState pywebview methods, existing firmware card controls, keyboard_models metadata. One bounded diagnostics helper, no persistent service or remote writer. Proof: deterministic long-outage, invalid/recovered sample, clock-discontinuity, terminal identity/power/config changes, worker-finalization, bundle metadata, descriptor privacy/issue URL and rendered UI checks. Hardware qualification is explicitly open.


Validation: 115 source unit tests pass (private supplier research fixtures excluded), 15 Node tests pass, macOS desktop bundle and source --check pass, code signature verified. A deterministic 641-retry outage exceeding ten hours recovers; a stale server reading retains its exact message. Gauge rejection/recovery, explicit clock discontinuities, immutable partial receipt on summary failure and terminal power/config changes pass. Native installed UI visibly collected a truthful empty USB report, kept installation disabled and exposed report review and GitHub draft controls. The rebuilt app is installed only in Applications, preserving the existing local Bluetooth helper. Actual new recording is still blocked on macOS Input Monitoring refresh; a fresh live check sees BT2 and the enrolled board but access is denied. No new recording has started. S75 physical qualification remains blocked on hardware.
