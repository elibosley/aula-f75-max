#!/usr/bin/env python3
"""Reproduce the installed 7c5a diagnostic offline under explicit clock assumptions."""
import hashlib
import json
import struct
from system_emulator import System, ROOT

image = ROOT / 'analysis/diagnostics/ea3dd9c1159c42f9b981ae76e1f2b0e2/image.bin'
expected = 'd5ce680b54ac7b7d5cf8da073ae9f59e4ac9edbd525a96ad967174d7219cee19'
assert hashlib.sha256(image.read_bytes()).hexdigest() == expected
# This archived image has no complete base ELF. Only vector-derived addresses
# and the fixed ROM boundary are used below; the symbol ELF supplies no code.
symbols_only = ROOT / 'analysis/flashed/c4d5d61510ec4b5490a1684a355702a7/f75max-wired-test.elf'
fault = struct.unpack_from('<I', image.read_bytes(), 12)[0] & ~1
cases = []
for clock, held, destination in [(0, False, 0x1fff0300), (8, False, fault),
                                 (0, True, 0x1fff0300), (8, True, 0x1fff0300)]:
    with System(image, ahbcp=clock, held=held, symbols_file=symbols_only) as machine:
        machine.until(destination)
        cases.append(dict(ahbcp=clock, wheel_held=held,
                          reached='rom_boundary' if destination == 0x1fff0300 else 'hard_fault_before_main'))
result = dict(status='passed', installed_image_sha256=expected, installed_checksum='7c5a',
              cases=cases, actual_hardware_handoff_value='not_measured',
              factory_rom_executed=False, hardware_writes=False,
              conclusion='The clock-divider bug can prevent the exact installed main checkpoint from running. ROM-boundary arrival does not prove ROM USB enumeration or physical wheel entry.')
(ROOT / 'analysis/installed-diagnostic-emulation.json').write_text(json.dumps(result, indent=2)+'\n')
print(json.dumps(result, indent=2))
