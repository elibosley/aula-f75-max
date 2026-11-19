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
from unicorn import UC_HOOK_MEM_READ
from unicorn.arm_const import UC_ARM_REG_R0

EXPECTED = 'bcc5f633d21f6219b9eebfec2c00b76a4f6bc3246babbe2e157478b26398d598'


def board_peripherals(data):
    """Replay GPIO truth tables and shared peripheral setup, with bounded stubs."""
    def literal(address, displacement):
        return struct.unpack_from('<I', data, ((address + 4) & ~3) + displacement)[0]

    index = literal(0x613a, 0x2d4)
    arrays = [literal(a, off) for a, off in [(0x6144,0x2cc),(0x6146,0x2d0),(0x6148,0x2d0)]]
    rows = []
    for row in range(21):
        machine = Firmware(data)
        for address in arrays:
            machine.cpu.mem_write(address, b'\1\0' * 147)
        machine.byte(index, row)
        machine.run(0x6138)
        assert len(machine.writes) == 1
        write = machine.writes[0]
        port = GPIO.index(write['address'] - 0x24)
        assert write['value'].bit_count() == 1
        rows.append('ABCD'[port] + str(write['value'].bit_length() - 1))
    columns = []
    for column in range(21):
        machine = Firmware(data)
        machine.byte(index, 0)
        machine.cpu.mem_write(arrays[0] + column * 2, b'\x37\0')
        machine.run(0x6034)
        hits = [w for w in machine.writes if w['value'] & 0xffff == 0x37]
        assert len(hits) == int(column < 15)
        if hits:
            columns.append(hits[0]['address'])

    inputs = {}
    for name, routine, output, combinations in [
        ('encoder', 0x21e0, 0x2000005b,
         [(a << 3,b,a*2+b) for a in range(2) for b in range(2)]),
        ('selector', 0x204c, 0x20000053,
         [(a << 10,b << 2,a*2+b) for a in range(2) for b in range(2)]),
        ('charging', 0x216a, 0x20000056,
         [(0,(a << 17) | (b << 16),(1-a)+b*2) for a in range(2) for b in range(2)]),
    ]:
        cases = []
        for port_a, port_b, expected in combinations:
            machine = Firmware(data)
            machine.word(GPIO[0], port_a)
            machine.word(GPIO[1], port_b)
            machine.run(routine)
            actual = machine.byte(output)
            assert actual == expected, (name, port_a, port_b, actual, expected)
            cases.append(dict(gpio_a=port_a,gpio_b=port_b,raw=actual))
        inputs[name] = dict(routine=hex(routine), cases=cases)

    gpio = Firmware(data, stubs=[0xb498])
    gpio.run(0x8e70)
    uart = Firmware(data)
    uart.run(0x13726)
    spi = Firmware(data)
    spi.run(0x1345c)
    timer = Firmware(data)
    def complete_reset(cpu, access, address, size, value, context):
        if address in [0x40000000,0x40002000,0x40004000,0x40006000,0x4000a000]:
            timer.word(address, timer.word(address) & ~2)
    timer.cpu.hook_add(UC_HOOK_MEM_READ, complete_reset)
    timer.run(0x13114)
    # Read-only gauge transaction: stub bit timing, ACK and returned byte.
    class GaugeFirmware(Firmware):
        def on_code(self, cpu, address, size, context):
            if address == 0x13826: cpu.reg_write(UC_ARM_REG_R0, 0)
            super().on_code(cpu, address, size, context)
    gauge = GaugeFirmware(data, stubs=[0x138be,0x13864,0x13826,0x13a02,0x13aa8,0x137f0])
    gauge.run(0x6e54, [4,0x20006000])
    sent = [c['args'][0] for c in gauge.calls if c['address'] == 0x13864]
    assert sent == [0xc6,4,0xc7]
    return dict(rgb=dict(rows=rows,columns=columns,initialization=timer.writes,
                         color_order='Physical color and strip direction require board checks'),
                inputs=inputs,gpio_initialization=gpio.writes,uart_initialization=uart.writes,
                spi_initialization=spi.writes,gauge=dict(register=4,sent=sent,
                stubbed_routines=['start','send_byte','ack','receive_byte','nack','stop']),
                timing='Peripheral completion modeled; electrical waveforms are not modeled')


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
                display=display, peripherals=board_peripherals(data), emulated_routines=['matrix_drive', 'matrix_sense', 'panel_init', 'panel_orientation'],
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
