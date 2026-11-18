#!/usr/bin/env python3
"""Replay the S75 Pro supplier matrix routines with bounded GPIO emulation.

Requires an operator-supplied, hash-matching extracted factory image. This
executes ARM routines in Unicorn and never opens a hardware connection.
"""
import argparse
import hashlib
import json
import struct
from pathlib import Path
from emulate import Firmware, GPIO

EXPECTED = 'bcc5f633d21f6219b9eebfec2c00b76a4f6bc3246babbe2e157478b26398d598'


def replay(image):
    data = Path(image).read_bytes()
    if hashlib.sha256(data).hexdigest() != EXPECTED:
        raise ValueError('S75 Pro V1.10 image identity mismatch')
    drive = []
    for row in range(15):
        machine = Firmware(data)
        machine.byte(0x2000018a, row)
        machine.run(0x3a84)
        writes = [entry for entry in machine.writes if entry['address'] in [base + 0x24 for base in GPIO]]
        if len(writes) != 1 or writes[0]['value'].bit_count() != 1:
            raise ValueError('Unexpected S75 matrix drive behavior')
        entry = writes[0]
        port = GPIO.index(entry['address'] - 0x24)
        drive.append(f'P{port}.{entry["value"].bit_length() - 1}')
    sense = []
    for port, base in enumerate(GPIO):
        for bit in range(20):
            machine = Firmware(data, stubs=[0x3b52, 0x3b3a, 0x3a84, 0x7faa])
            machine.word(base, 1 << bit)
            value = machine.run(0x3b74)
            if value:
                if value.bit_count() != 1:
                    raise ValueError('Ambiguous S75 sense input')
                sense.append(dict(pin=f'P{port}.{bit}', sense_bit=value.bit_length() - 1))
    if sorted(entry['sense_bit'] for entry in sense) != list(range(6)):
        raise ValueError('S75 sense inputs are incomplete')
    panel = Firmware(data, stubs=[0x1345c, 0x7f78, 0x7a4c, 0x7a44])
    panel.run(0x7afc)
    commands = []
    for call in panel.calls:
        if call['address'] == 0x7a4c:
            commands.append(dict(command=call['args'][0], data=[]))
        elif call['address'] == 0x7a44:
            if not commands:
                raise ValueError('Panel data appeared before a command')
            commands[-1]['data'].append(call['args'][0])
    offset_address = struct.unpack_from('<I', data, ((0x7a6c + 4) & ~3) + 0x3dc)[0]
    display = dict(init_commands=commands, offset_x=panel.byte(offset_address),
                   offset_y=panel.byte(offset_address + 1),
                   gpio_writes=panel.writes,
                   stubbed_routines=['spi_initialization', 'millisecond_delay',
                                     'panel_command_output', 'panel_data_output'],
                   physical_verified=False)
    return dict(status='passed', supplier_image_sha256=EXPECTED, drive_pins=drive,
                sense_pins=sorted(sense, key=lambda entry: entry['sense_bit']),
                display=display, emulated_routines=['matrix_drive', 'matrix_sense', 'panel_init', 'panel_orientation'],
                stubbed_routines=['configure_matrix_outputs', 'clear_matrix_outputs',
                                  'select_matrix_drive', 'settle_delay'],
                full_system_emulated=False, hardware_tested=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('image', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = json.dumps(replay(args.image), indent=2) + '\n'
    if args.output:
        args.output.write_text(result)
    print(result)
