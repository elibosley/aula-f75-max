#!/usr/bin/env python3
"""Bounded emulation of extracted firmware routines. No USB/device access."""
import json
from pathlib import Path
import struct

from unicorn import Uc, UC_ARCH_ARM, UC_MODE_MCLASS, UC_MODE_THUMB, UC_HOOK_CODE, UC_HOOK_MEM_WRITE
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3
from unicorn.arm_const import UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PC

ROOT = Path(__file__).resolve().parents[1]
APPLICATION = ROOT / "analysis/firmware/supplier-f75max-firmware/application.bin"
STOP = 0x3F000
GPIO = [0x40044000, 0x40046000, 0x40048000, 0x4004A000]


class Firmware:
    def __init__(self, data=None, stubs=()):
        self.cpu = Uc(UC_ARCH_ARM, UC_MODE_THUMB | UC_MODE_MCLASS)
        self.cpu.mem_map(0, 0x40000)
        self.cpu.mem_write(0, data if data is not None else APPLICATION.read_bytes())
        self.cpu.mem_map(0x20000000, 0x10000)
        self.cpu.mem_map(0x40000000, 0x80000)
        self.cpu.mem_map(0xE000E000, 0x2000)
        self.stubs = set(stubs)
        self.calls = []
        self.writes = []
        self.completed = False
        self.cpu.hook_add(UC_HOOK_CODE, self.on_code)
        self.cpu.hook_add(UC_HOOK_MEM_WRITE, self.on_write)

    def byte(self, address, value=None):
        if value is not None:
            self.cpu.mem_write(address, bytes([value]))
        return self.cpu.mem_read(address, 1)[0]

    def word(self, address, value=None):
        if value is not None:
            self.cpu.mem_write(address, struct.pack("<I", value))
        return struct.unpack("<I", self.cpu.mem_read(address, 4))[0]

    def on_code(self, cpu, address, size, _):
        if address == STOP:
            self.completed = True
            cpu.emu_stop()
        elif address in self.stubs:
            self.calls.append({"address": address, "args": [cpu.reg_read(r) for r in
                               [UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3]]})
            cpu.reg_write(UC_ARM_REG_PC, cpu.reg_read(UC_ARM_REG_LR))

    def on_write(self, cpu, access, address, size, value, _):
        if 0x40000000 <= address < 0x40080000:
            self.writes.append({"address": address, "size": size, "value": value,
                                "instruction": cpu.reg_read(UC_ARM_REG_PC)})
            for base in GPIO:
                if address in (base + 0x24, base + 0x28):
                    previous = self.word(base)
                    self.word(base, previous | value if address == base + 0x24 else previous & ~value)

    def run(self, address, args=()):
        self.completed = False
        self.cpu.reg_write(UC_ARM_REG_SP, 0x2000F000)
        self.cpu.reg_write(UC_ARM_REG_LR, STOP | 1)
        for reg, value in zip([UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3], args):
            self.cpu.reg_write(reg, value)
        self.cpu.emu_start(address | 1, STOP + 2, timeout=1000000, count=100000)
        if not self.completed:
            raise RuntimeError(f"Routine {address:#x} did not return within emulator bounds")
        return self.cpu.reg_read(UC_ARM_REG_R0)


def encoder(sequence, menu=False, data=None, stable_calls=6):
    fw = Firmware(data, stubs=[0x4564, 0x107A8, 0x101B8])
    fw.byte(0x2000004E, int(menu))
    observations = []
    for state in sequence:
        fw.word(GPIO[0], ((state & 1) << 2) | ((state & 2) << 2))
        for _ in range(stable_calls):
            fw.run(0x21F0)
        observations.append({"state": state, "consumer_usage": fw.byte(0x2000007B),
                             "queue_events": [c["args"][0] for c in fw.calls if c["address"] == 0x107A8]})
    return observations


def matrix_outputs():
    outputs = []
    for index in range(18):
        fw = Firmware()
        fw.byte(0x20000185, index)
        fw.run(0x39F6)
        outputs.append({"scan_index": index, "writes": fw.writes})
    return outputs


def display_init():
    # Capture command/data calls. Do not model SPI timing or panel behavior.
    fw = Firmware(stubs=[0x8DB8, 0x7D98, 0x68EC, 0x68E4, 0x6994])
    fw.run(0x69F6)
    return {"calls": fw.calls, "writes": fw.writes,
            "offset_x": fw.byte(0x200001D6), "offset_y": fw.byte(0x200001D7)}


def main():
    sequences = {"cycle_a": [3, 2, 0, 1, 3], "cycle_b": [3, 1, 0, 2, 3]}
    result = {"scope": "Emulated firmware with external callees stubbed. Not a physical hardware test.",
              "wheel": {mode: {name: encoder(seq, mode == "menu") for name, seq in sequences.items()}
                        for mode in ["media", "menu"]}, "matrix_outputs": matrix_outputs(),
              "display_init": display_init()}
    target = ROOT / "analysis" / "emulation.json"
    target.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
