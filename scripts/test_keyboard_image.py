#!/usr/bin/env python3
"""Exercise linked ARM board adapters with modeled GPIO, USB and scheduling.

This checks machine code from the candidate image. It cannot validate physical
pin polarity, panel/radio electronics, USB enumeration, or ROM recovery.
"""
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess

from unicorn import UC_HOOK_MEM_READ, UC_HOOK_MEM_WRITE, UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3
from unicorn.arm_const import UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PC, UC_ARM_REG_PRIMASK
from emulate import Firmware, GPIO, STOP

ROOT = Path(__file__).resolve().parents[1]
IMAGE = Path(os.environ.get('F75_IMAGE', ROOT / 'analysis/UNFLASHED/f75max-wired-test.bin')).resolve()
ELF = IMAGE.with_suffix('.elf')
NM = ROOT / 'builddeps/arm-toolchain/bin/arm-none-eabi-nm'
BOARD = json.loads((ROOT / 'firmware/targets/f75max/board-map.json').read_text())
SYMBOLS = {}
for line in subprocess.check_output([str(NM), '-n', str(ELF)], text=True).splitlines():
    parts = line.split()
    if len(parts) == 3:
        SYMBOLS[parts[2]] = int(parts[0], 16)


SCRATCH=(SYMBOLS['__heap_base__']+15)&~15
TILE=SCRATCH+0x400
assert TILE+2048<0x20007e00, 'Model scratch overlaps firmware globals or stack'


def pin(name):
    port, bit = name[1:].split('.')
    return GPIO[int(port)], 1 << int(bit)


class Candidate(Firmware):
    def __init__(self):
        self.now = 1000
        self.events = []
        self.pressed = set()
        self.model_matrix = False
        self.timer4_ticks=0
        self.drive = [pin(p) for p in BOARD['matrix']['drive_pins']]
        self.sense = [pin(p['pin']) for p in BOARD['matrix']['sense_pins']]
        self.callbacks = {}
        super().__init__(IMAGE.read_bytes())
        size = SYMBOLS['__data_end__'] - SYMBOLS['__data_base__']
        self.cpu.mem_write(SYMBOLS['__data_base__'], bytes(self.cpu.mem_read(SYMBOLS['__textdata_base__'], size)))
        self.cpu.hook_add(UC_HOOK_MEM_READ, self.read_gpio)
        self.callback('chThdSleep', lambda args: 0)
        self.callback('timer_read32', lambda args: self.now)
        for name in ['chVTDoSetI', 'chSysLock', 'chSysUnlock']:
            if name in SYMBOLS: self.callback(name, lambda args: 0)
        for name in ['register_code16', 'unregister_code16', 'clear_keyboard', 'bootloader_jump']:
            self.callback(name, lambda args, n=name: self.events.append((n, args[0])) or 0)
        self.word(GPIO[0], 1 << 10)
        self.word(GPIO[1], (1 << 2) | (1 << 17))

    def callback(self, name, callback):
        self.callbacks[SYMBOLS[name]] = callback

    def on_code(self, cpu, address, size, data):
        if address in self.callbacks:
            args = [cpu.reg_read(r) for r in [UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3]]
            value = self.callbacks[address](args)
            cpu.reg_write(UC_ARM_REG_R0, value or 0)
            cpu.reg_write(UC_ARM_REG_PC, cpu.reg_read(UC_ARM_REG_LR))
        else:
            super().on_code(cpu, address, size, data)

    def read_gpio(self, cpu, access, address, size, value, data):
        if address==0x40008004:
            self.timer4_ticks=(self.timer4_ticks+1)&65535;self.word(address,self.timer4_ticks);return
        if not self.model_matrix or address not in GPIO:
            return
        active = [i for i, (base, mask) in enumerate(self.drive) if self.word(base) & self.word(base+4) & mask]
        assert len(active) <= 1, ('multiple matrix lines asserted', active)
        current = self.word(address)
        for base, mask in self.sense:
            if base == address:
                current &= ~mask
        for row, col in self.pressed:
            base, mask = self.sense[col]
            if row in active and base == address:
                current |= mask
        self.word(address, current)

    def on_write(self, cpu, access, address, size, value, data):
        if address == 0xe000ed0c and value & 4:
            self.events.append(('system_reset_requested', value))
            self.completed = True
            cpu.emu_stop()
        else:
            super().on_write(cpu, access, address, size, value, data)

    def call(self, name, *args):
        self.completed = False
        self.cpu.reg_write(UC_ARM_REG_SP, 0x20007f00)
        self.cpu.reg_write(UC_ARM_REG_LR, STOP | 1)
        for register, value in zip([UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3], args):
            self.cpu.reg_write(register, value)
        self.cpu.emu_start(SYMBOLS[name] | 1, STOP + 2, timeout=2000000, count=1500000 if name in ('f75_render_tile','f75_sprite_decode','housekeeping_task_user') else 300000)
        assert self.completed, ('did not return within emulator bound', name)
        return self.cpu.reg_read(UC_ARM_REG_R0)

    def key(self, row, col, down):
        code = struct.unpack('<H', self.cpu.mem_read(SYMBOLS['keymaps'] + (row * 6 + col) * 2, 2))[0]
        # This target uses QMK's short enum keyevent_t: col,row,time,type,pressed.
        self.cpu.mem_write(SCRATCH+0x100, struct.pack('<BBHBB', col, row, self.now & 0xffff, 1, down))
        assert self.call('process_record_user', code, SCRATCH+0x100) == 0

    def initialize_app(self, arm=True):
        if 'f75_panel_init' in SYMBOLS:
            self.callback('f75_panel_init', lambda args: 0)  # don't model the panel while checking key ownership
        self.call('keyboard_post_init_user')
        if arm:
            self.call('matrix_init_custom')
            if 'f75_matrix_sample' in SYMBOLS:
                for _ in range(30):self.call('begin_row')
            self.call('matrix_scan_custom', SCRATCH+0x20)
            self.now += 25
            if 'f75_matrix_sample' in SYMBOLS:
                for _ in range(30):self.call('begin_row')
            self.call('matrix_scan_custom', SCRATCH+0x20)
        self.byte(SYMBOLS['USBD1'],4)  # configured USB state for the isolated adapter fixture
        self.events.clear()


def matrix_test():
    fw = Candidate()
    fw.call('matrix_init_custom')
    fw.model_matrix = True
    address = SCRATCH+0x10
    fw.cpu.mem_write(address - 1, b'\xa5' + bytes(15) + b'\x5a')
    assert fw.call('matrix_scan_custom', address) == 0
    for row in range(15):
        for col in range(6):
            fw.pressed = {(row, col)}
            assert fw.call('matrix_scan_custom', address) == 1
            expected = bytearray(15); expected[row] = 1 << col
            assert bytes(fw.cpu.mem_read(address, 15)) == bytes(expected), (row, col)
            assert fw.call('matrix_scan_custom', address) == 0
            fw.pressed.clear()
            assert fw.call('matrix_scan_custom', address) == 1
            assert not any(fw.cpu.mem_read(address, 15))
    fw.pressed = {(0, 3), (1, 3), (6, 5), (14, 5)}
    assert fw.call('matrix_scan_custom', address) == 1
    assert list(fw.cpu.mem_read(address, 15)) == [8, 8, 0, 0, 0, 0, 32, 0, 0, 0, 0, 0, 0, 0, 32]
    assert fw.byte(address - 1) == 0xa5 and fw.byte(address + 15) == 0x5a
    assert all(not fw.word(base) & mask for base, mask in fw.drive)
    return dict(single_coordinates=90, stable_scans=90, release_scans=90, chord=True, bounds=True)


def key_test():
    unarmed = Candidate(); unarmed.initialize_app(arm=False)
    unarmed.key(0, 3, True); unarmed.key(0, 3, False)
    assert not unarmed.events
    fw = Candidate(); fw.initialize_app()
    for (row, col), mapped in [((0, 3), 0xe3), ((0, 5), 0x39), ((2, 5), 0xe3)]:
        fw.events.clear(); fw.key(row, col, True); fw.key(row, col, False)
        assert fw.events == [('register_code16', mapped), ('unregister_code16', mapped)], fw.events
    # A profile change releases old mappings; their later key-up cannot release
    # a newly registered mapping owned by a different physical key.
    fw.key(2, 5, True)
    fw.key(11, 5, True)  # Fn
    fw.events.clear(); fw.key(8, 4, True)  # Fn+M
    assert [event[0] for event in fw.events] == ['clear_keyboard']
    fw.events.clear(); fw.key(2, 5, False)
    assert not fw.events
    fw.key(8, 4, False); fw.key(11, 5, False)
    fw.key(2, 5, True); fw.key(2, 5, False)
    assert fw.events == [('register_code16', 0xe2), ('unregister_code16', 0xe2)]
    # Whole-board control input cannot reach the host.
    fw.events.clear(); fw.key(11, 5, True); fw.key(6, 5, True)
    fw.key(1, 3, True); fw.key(1, 3, False)
    assert all(event[0] == 'clear_keyboard' for event in fw.events)
    fw.key(6, 5, False); fw.key(11, 5, False)
    fw.events.clear(); fw.key(1, 3, True); fw.key(1, 3, False)
    assert fw.events == [('register_code16', 4), ('unregister_code16', 4)]
    # A physical selector movement clears the temporary USB hotkey override.
    fw.word(GPIO[0], 0); fw.call('housekeeping_task_user'); fw.now += 21; fw.call('housekeeping_task_user')
    fw.events.clear(); fw.key(1, 3, True); fw.key(1, 3, False)
    assert not fw.events
    fw.key(11, 5, True); fw.key(5, 1, True); fw.key(5, 1, False); fw.key(11, 5, False)  # Fn+5
    fw.events.clear(); fw.key(1, 3, True); fw.key(1, 3, False)
    assert len(fw.events) == 2
    fw.word(GPIO[0], 1 << 10); fw.word(GPIO[1], 1 << 17)
    fw.call('housekeeping_task_user'); fw.now += 21; fw.call('housekeeping_task_user')
    fw.events.clear(); fw.key(1, 3, True); fw.key(1, 3, False)
    assert not fw.events
    return dict(startup_suppression=True, caps_ctrl=True, mac_windows=True, mapping_release=True, control_layer=True, selector_override=True)


def panel_test():
    fw = Candidate(); stream = []; sleeps=[]
    fw.callback('chThdSleep',lambda args:sleeps.append(args[0]) or 0)
    fw.callback('spi_init', lambda args: 0)
    fw.callback('spi_start_extended', lambda args: 1)
    fw.callback('spi_stop', lambda args: 0)
    if 'f75_panel_transfer' in SYMBOLS:
        fw.callback('f75_panel_transfer', lambda args: stream.append(('data' if fw.word(GPIO[3]) & (1 << 14) else 'command', bytes(fw.cpu.mem_read(args[0], args[1])))) or 1)
        if 'f75_panel_pixels' in SYMBOLS:
            fw.callback('f75_panel_pixels', lambda args: stream.append(('data', b''.join(struct.pack('>H',p[0]) for p in struct.iter_unpack('<H',bytes(fw.cpu.mem_read(args[0],args[1]*2)))))) or 1)
    else:
        fw.callback('spi_write', lambda args: stream.append(('data' if fw.word(GPIO[3]) & (1 << 14) else 'command', bytes([args[0] & 255]))) or 0)
        fw.callback('spi_transmit', lambda args: stream.append(('data', bytes(fw.cpu.mem_read(args[0], args[1])))) or 0)
    fw.word(0x40042010, 0xf500)
    assert fw.call('f75_panel_init') == 1
    assert sleeps==[3750,3750,28125,37500],sleeps
    assert fw.word(0x40042010) == 0xf5bf
    expected = []
    for c in BOARD['display']['init_commands']:
        expected.append(('command', bytes([int(c['command'], 16)])))
        if c['data']: expected.append(('data', bytes(c['data'])))
    assert stream == expected
    stream.clear()
    fw.cpu.mem_write(TILE, struct.pack('<128H', *([0xf800, 0x07e0, 0x001f, 0xffff] * 32)))
    assert fw.call('f75_panel_tile', 7, 1, TILE) == 1
    assert stream[:5] == [('command', b'\x2a'), ('data', b'\x00\x02\x00\x81'),
                          ('command', b'\x2b'), ('data', b'\x00\x08\x00\x08'), ('command', b'\x2c')]
    assert b''.join(data for kind, data in stream[5:]) == b'\xf8\x00\x07\xe0\x00\x1f\xff\xff' * 32
    for y, rows, pointer in [(127, 2, TILE), (0, 0, TILE), (0, 9, TILE), (0, 1, 0)]:
        stream.clear(); assert fw.call('f75_panel_tile', y, rows, pointer) == 0; assert not stream
    return dict(stock_reset_delays=True,stock_initialization=True, pin_mux_preserved=True, window_offsets=True, rgb565_byte_order=True, invalid_tiles_rejected=True)


def boot_shortcut_test():
    fw = Candidate(); fw.call('keyboard_pre_init_user')
    assert not fw.events
    fw.word(GPIO[1], 1 << 2); fw.call('keyboard_pre_init_user')
    assert not fw.events, 'late initialization repeated the reset-owned recovery gesture'
    fw = Candidate(); fw.initialize_app()
    fw.key(11, 5, True); fw.key(0, 0, True)  # Fn+Escape
    fw.now += 1199; fw.call('housekeeping_task_user')
    assert not any(name == 'bootloader_jump' for name, value in fw.events)
    fw.now += 1; fw.call('housekeeping_task_user')
    assert sum(name == 'bootloader_jump' for name, value in fw.events) == 1
    fw.call('housekeeping_task_user')
    assert sum(name == 'bootloader_jump' for name, value in fw.events) == 1
    fw = Candidate(); fw.initialize_app()
    fw.key(11, 5, True); fw.key(0, 0, True); fw.key(0, 0, False)
    fw.now += 1201; fw.call('housekeeping_task_user')
    assert not any(name == 'bootloader_jump' for name, value in fw.events)
    return 'Fn+Escape hold/cancel checked; the reset guard exclusively owns boot-time wheel entry'


def health_test():
    fw = Candidate(); fw.initialize_app(); replies = []
    fw.callback('raw_hid_send', lambda args: replies.append(bytes(fw.cpu.mem_read(args[0], args[1]))) or 0)
    address = SCRATCH
    request = b'F75?' + struct.pack('<I', 0x12345678) + bytes(24)
    fw.cpu.mem_write(address, request); fw.call('raw_hid_receive', address, 32)
    assert len(replies) == 1 and len(replies[0]) == 32
    assert replies[0][:8] == b'F75!' + struct.pack('<I', 0x12345678)
    assert struct.unpack_from('<I', replies[0], 8)[0] == fw.now
    assert replies[0][24] == 10 and replies[0][28:31] == bytes([1, 1, 0])
    fw.cpu.mem_write(address, b'BAD!' + bytes(28)); fw.call('raw_hid_receive', address, 32)
    assert len(replies) == 1
    fw.call('raw_hid_receive', 0, 16)
    # A deliberate boot command is acknowledged before the deferred jump.
    fw.cpu.mem_write(address, b'F75B' + bytes(4) + bytes.fromhex('aa42895aff7162cc') + bytes(16))
    fw.call('raw_hid_receive', address, 32)
    assert len(replies) == 2
    fw.now += 49; fw.call('housekeeping_task_user')
    assert not any(n == 'bootloader_jump' for n, value in fw.events)
    fw.now += 1; fw.call('housekeeping_task_user')
    assert sum(n == 'bootloader_jump' for n, value in fw.events) == 1
    return dict(nonce_echo=True, bounded_readonly_response=True, unknown_packets_ignored=True, deferred_explicit_boot=True)


def gpio_snapshot_test():
    fw = Candidate(); replies = []
    fw.callback('raw_hid_send', lambda args: replies.append(bytes(fw.cpu.mem_read(args[0], args[1]))) or 0)
    expected = [0x11223344, 0x55667788, 0x12345678, 0x87654321, 0xaabbccdd, 0x12345678]
    for address, value in zip([*GPIO, GPIO[1]+4, GPIO[1]+0x30], expected):
        fw.word(address, value)
    pointer = SCRATCH
    fw.cpu.mem_write(pointer, b'F75Gtest' + b'\xff' * 24)
    before = len(fw.writes)
    fw.call('raw_hid_receive', pointer, 32)
    assert replies == [b'F75Htest' + struct.pack('<6I', *expected)]
    assert len(fw.writes) == before, 'GPIO diagnostics changed peripheral state'
    return dict(fixed_registers_only=True, nonce_echo=True, peripheral_writes=False)


def auxiliary_snapshot_test():
    fw = Candidate(); replies = []
    fw.callback('raw_hid_send', lambda args: replies.append(bytes(fw.cpu.mem_read(args[0], args[1]))) or 0)
    expected = [0] * 15
    for coordinate in BOARD['matrix']['coordinates']:
        if not coordinate.get('vendor_key'):
            expected[coordinate['scan_index']] |= 1 << coordinate['sense_bit']
    fw.cpu.mem_write(SYMBOLS['matrix'], bytes([63] * 15))
    pointer = SCRATCH
    fw.cpu.mem_write(pointer, b'F75Ktest' + bytes(24))
    before = len(fw.writes)
    fw.call('raw_hid_receive', pointer, 32)
    assert replies == [b'F75Ltest' + bytes(expected) + bytes([1, 1]) + bytes(7)]
    assert len(fw.writes) == before, 'switch diagnostics changed peripheral state'
    return dict(unassigned_positions_only=True, typing_keys_masked=True, nonce_echo=True, peripheral_writes=False)


def wheel_matrix_button_test():
    fw = Candidate(); fw.initialize_app()
    fw.word(GPIO[1], 1 << 2)  # Actual unused P1.17 input remains low.
    def settle(value, elapsed):
        fw.cpu.mem_write(SYMBOLS['matrix'] + 14, bytes([value]))
        fw.now += elapsed; fw.call('housekeeping_task_user')
        fw.now += 21; fw.call('housekeeping_task_user')
    settle(0, 30)
    assert fw.byte(SYMBOLS['navigation']) == 0
    settle(1, 1); settle(0, 80)
    assert fw.byte(SYMBOLS['navigation']) == 1, 'matrix wheel click did not open menu'
    settle(1, 1)
    fw.now+=649;fw.call('housekeeping_task_user')
    assert fw.byte(SYMBOLS['navigation'])==1,'Back fired before the hold threshold'
    fw.now+=1;fw.call('housekeeping_task_user')
    assert fw.byte(SYMBOLS['navigation'])==0,'Back did not fire while held'
    fw.now+=700;fw.call('housekeeping_task_user')
    assert fw.byte(SYMBOLS['navigation'])==0,'One hold fired Back more than once'
    settle(0,20)
    assert fw.byte(SYMBOLS['navigation'])==0,'Release after Back caused a click'
    settle(1,1);fw.now+=700;fw.call('housekeeping_task_user');settle(0,20)
    assert fw.byte(SYMBOLS['navigation'])==0,'Back on Home opened the menu'
    return dict(matrix_row=14, matrix_col=0, click_opens_menu=True, hold_returns_home=True,back_fires_while_held=True,release_does_not_click=True,back_on_home_is_noop=True, unused_p1_17_low_ignored=True)


def performance_snapshot_test():
    fw = Candidate(); replies = []
    fw.callback('raw_hid_send', lambda args: replies.append(bytes(fw.cpu.mem_read(args[0], args[1]))) or 0)
    names = ['perf_tiles','perf_render_ticks','perf_spi_ticks','perf_max_render','perf_max_spi','f75_max_scan_gap_ticks']
    values = [100, 200, 300, 4, 5, 6]
    for name, value in zip(names, values): fw.word(SYMBOLS[name], value)
    pointer = SCRATCH
    fw.cpu.mem_write(pointer, b'F75Ptest' + bytes(24))
    before = len(fw.writes)
    fw.call('raw_hid_receive', pointer, 32)
    assert replies == [b'F75Qtest' + struct.pack('<6I', *values)]
    assert len(fw.writes) == before
    return dict(fixed_counters_only=True, nonce_echo=True, peripheral_writes=False)


def startup_guard_test():
    fw = Candidate()
    fw.call('startup_guard', 0, 0)
    assert fw.word(0x20007ffc) == 0xdeadbeef
    assert len(fw.events) == 1 and fw.events[0][0] == 'system_reset_requested'
    fw = Candidate(); fw.word(SYMBOLS['complete_frames'], 1)
    fw.call('startup_guard', 0, 0)
    assert not fw.events
    return 'modeled missing first frame requests ROM-reset magic; completed frame does not reset'


def reset_recovery_test():
    """Start at the real reset vector with uninitialized C RAM and no HAL stubs."""
    image = IMAGE.read_bytes()
    build = json.loads(IMAGE.with_suffix('.json').read_text())
    guard = build['reset_recovery']
    assert hashlib.sha256(image[guard['start']:guard['end']]).hexdigest() == guard['sha256']
    assert struct.unpack_from('<I', image, 4)[0] & ~1 == guard['start']
    cases = []
    for held, magic, expected in [(False, False, 'runtime'), (True, False, 'rom'),
                                  (False, True, 'rom'), (True, True, 'rom')]:
        fw = Firmware(image)
        fw.cpu.mem_map(0x1fff0000, 0x1000)
        fw.cpu.mem_write(0x20000000, b'\xa5' * 0x8000)
        fw.word(0x20007ffc, 0xdeadbeef if magic else 0)
        before_ram = bytes(fw.cpu.mem_read(0x20000000, 0x8000))
        fw.word(GPIO[1], 0)  # The unrelated P1.17 input must not control entry.
        def wheel_sense(cpu, access, address, size, value, data):
            if address == GPIO[1]:
                active = held and bool(fw.word(GPIO[2]) & (1 << 9))
                fw.word(GPIO[1], (1 << 14) if active else 0)
        fw.cpu.hook_add(UC_HOOK_MEM_READ, wheel_sense)
        fw.word(GPIO[1] + 4, 0xffffffff)
        fw.word(GPIO[1] + 8, 0xffffffff)
        fw.word(GPIO[1] + 0x30, 0xffffffff)
        reached = []
        def checkpoint(cpu, address, size, data):
            if address in (SYMBOLS['_crt0_entry'], 0x1fff0300):
                reached.append('rom' if address == 0x1fff0300 else 'runtime')
                cpu.emu_stop()
        fw.cpu.hook_add(UC_HOOK_CODE, checkpoint)
        sp, entry = struct.unpack_from('<II', image)
        fw.cpu.reg_write(UC_ARM_REG_SP, sp)
        fw.cpu.emu_start(entry, 0x1fff0400, timeout=2000000, count=200000)
        assert reached == [expected], (held, magic, reached)
        if not magic:
            assert fw.word(GPIO[1] + 4) == 0xffffbfff
            assert fw.word(GPIO[1] + 8) == 0xefffffff
            assert fw.word(GPIO[1] + 0x30) == 0xffffffff
            assert fw.word(GPIO[2]) & 0x43ff == 0, 'matrix drives left asserted'
        after_ram = bytes(fw.cpu.mem_read(0x20000000, 0x8000))
        if expected == 'rom':
            assert after_ram[:0x348] == bytes(0x348), 'factory ROM runtime RAM was not initialized'
            assert before_ram[0x348:-8] == after_ram[0x348:-8]
            assert fw.word(0x20007ff8) == 0x52543546
            assert fw.word(0x20007ffc) == 0
            assert fw.word(0x40060024) == 0, 'handoff remapped flash before leaving it'
            assert fw.cpu.reg_read(UC_ARM_REG_SP) == 0x20000348
            assert fw.cpu.reg_read(UC_ARM_REG_PRIMASK) == 0, 'ROM inherited masked USB interrupts'
        else:
            assert before_ram[:-4] == after_ram[:-4], 'normal reset used C RAM or stack'
            assert fw.cpu.reg_read(UC_ARM_REG_PRIMASK) == 1
        cases.append(dict(wheel_held=held, software_magic=magic, reached=expected))
    warm_cases = []
    for held in [False, True]:
        fw = Firmware(image)
        fw.word(0x20007ff8, 0x52543546)
        fw.word(GPIO[1], (1 << 14) if held else 0)
        def warm_entry(cpu,address,size,data):
            if address == SYMBOLS['_crt0_entry']:
                fw.completed = True; cpu.emu_stop()
        fw.cpu.hook_add(UC_HOOK_CODE, warm_entry)
        fw.cpu.reg_write(UC_ARM_REG_SP, struct.unpack_from('<I',image)[0])
        fw.cpu.emu_start(struct.unpack_from('<I',image,4)[0], 0x3ffff, timeout=1000000, count=200000)
        assert fw.completed and fw.word(0x20007ff8) == 0
        warm_cases.append(dict(wheel_held=held, explicit_rom_return_reaches_runtime=True))
    return dict(cases=cases, protected_sha256=guard['sha256'],
                warm_exit_cases=warm_cases,
                before_c_runtime=True, timer_or_hal_dependencies=False,
                physical_entry_verified=False)


def clock_divider_test():
    cases = []
    for value in range(16):
        fw = Candidate()
        fw.word(0x4006000c, 0x44)  # PLL selected and running at the configured 48 MHz
        fw.word(0x40060010, value)
        fw.call('SystemCoreClockUpdate')
        expected = 48000000 // (1 << (value & 7))
        if value & 8:
            expected = expected * 2 // 3
        measured = fw.word(SYMBOLS['SystemCoreClock'])
        assert measured == expected, (value, measured, expected)
        cases.append(dict(AHBCP=value, core_hz=measured))
    return dict(valid_register_states=cases, hardware_handoff_register='not_measured')


def rgb_test():
    fw=Candidate();fw.call('matrix_init_custom');fw.call('f75_rgb_init')
    assert fw.word(0x40042000)==0x3302 and fw.word(0x40042004)==0x700
    assert fw.word(0x40042018)==1
    assert fw.word(GPIO[0]+4)&0xf0==0 and fw.word(GPIO[2]+4)&0x43ff==0, 'GPIO outputs still own PWM pads'
    assert fw.word(0x400020a4)==0x7f0, 'RGB stole unassigned encoder PWM channels'
    assert fw.word(0x40000098)&0xf00000==0xf00000
    assert fw.word(0x40004098)&0xf00000==0xf00000
    # PWM hardware ends a row even if its IRQ never runs again.
    for base in [0x40000000,0x40004000]:
        assert fw.word(base+0x44)&0xffff==255 and fw.word(base+0x14)&(1<<23)
    assert fw.word(0x40002050)&0xffff==255 and fw.word(0x40002018)&(1<<8)
    fw.call('keyboard_pre_init_user')
    assert fw.word(GPIO[0])&0xe000==0xe000 and fw.word(GPIO[0]+4)&0xe000==0xe000
    assert fw.word(GPIO[1])&0x40003==0 and fw.word(GPIO[1]+4)&0x40003==0x40003
    before=fw.word(0x40008000)
    fw.word(0x40006004,77)
    fw.call('f75_rgb_pause')
    assert fw.word(0x40006000)==1 and fw.word(0x40006004)==77
    assert fw.word(0x400020a4)==0
    for base in [0x40000000,0x40004000]:assert fw.word(base+0x98)&0xffffff==0
    masks=[0xb00,0x30,0x3c00,0x73f00]
    assert all(not(fw.word(base)&mask) for base,mask in zip(GPIO,masks))
    fw.call('f75_rgb_resume');assert fw.word(0x400020a4)==0x7f0
    assert fw.word(0x40006004)==77, 'key scan restarted the lighting phase'
    fw.call('f75_rgb_suspend',1);fw.call('f75_rgb_resume')
    assert fw.word(0x400020a4)==0
    fw.call('f75_rgb_suspend',0);assert fw.word(0x400020a4)==0x7f0
    assert fw.word(0x40008000)==before, 'RGB changed the RTOS free counter'
    fw.call('f75_init',SYMBOLS['state'],0,0)
    fw.byte(SYMBOLS['USBD1'],4) # this case measures full-brightness USB operation
    fw.call('f75_rgb_tick',SYMBOLS['state'],1000)
    data=bytes(fw.cpu.mem_read(SYMBOLS['duties'],540))
    assert any(data) and max(data)<=35
    for effect in range(5):
        for level in [0,28,100]:
            trial=Candidate();trial.call('f75_rgb_init')
            trial.call('f75_init',SYMBOLS['state'],0,0)
            trial.byte(SYMBOLS['USBD1'],4)
            trial.byte(SYMBOLS['state']+104,level)
            trial.byte(SYMBOLS['state']+106,effect)
            trial.call('f75_rgb_tick',SYMBOLS['state'],1000)
            data=bytes(trial.cpu.mem_read(SYMBOLS['duties']+270,270))
            assert max(data)<=127
            if not level:assert not any(data)
            if effect==0:
                for channel,color in enumerate([145,226,206]):
                    assert set(data[channel*90:(channel+1)*90])=={color*(level*127//100)//255}
    # The full-key snapshot is driven by fixed IRQ samples, not main-loop redraws.
    live=Candidate();live.call('matrix_init_custom');live.model_matrix=True;live.call('f75_rgb_init')
    pointer=SCRATCH+0x10
    for row in range(15):
        for col in range(6):
            live.pressed={(row,col)}
            for _ in range(30):live.call('begin_row')
            live.call('matrix_scan_custom',pointer)
            expected=bytearray(15);expected[row]=1<<col
            assert bytes(live.cpu.mem_read(pointer,15))==bytes(expected)
    before=len(live.writes);live.call('matrix_scan_custom',pointer)
    assert not live.writes[before:], 'main-loop snapshot changed shared pins'
    maximum_delta=0
    for effect in range(5):
        trial=Candidate();trial.call('f75_rgb_init');trial.call('f75_init',SYMBOLS['state'],0,0)
        trial.byte(SYMBOLS['USBD1'],4)
        trial.byte(SYMBOLS['state']+104,100);trial.byte(SYMBOLS['state']+105,100)
        trial.byte(SYMBOLS['state']+106,effect)
        previous=first=None
        for now in range(1000,7001,25):
            # Consume the completed buffer without modeling an optical output.
            trial.byte(SYMBOLS['pending'],0)
            trial.call('f75_rgb_tick',SYMBOLS['state'],now)
            data=bytes(trial.cpu.mem_read(SYMBOLS['duties']+270,270))
            assert min(data)>0, ('animated key blackout',effect,now)
            if first is None:first=data
            if previous is not None:
                delta=max(abs(a-b) for a,b in zip(previous,data));maximum_delta=max(maximum_delta,delta)
                assert delta<=4,('abrupt lighting change',effect,now,delta)
                if effect==0:assert data==first,'Still animated'
            previous=data
        assert data==first, ('cycle discontinuity',effect)
    return dict(stock_pwm_channels_disabled_between_rows=True,stock_board_outputs_initialized=True,gpio_released_for_pwm=True,shared_irq_matrix_coordinates=90,main_loop_snapshot_has_no_peripheral_writes=True,calm_effects_maximum_pwm_delta_per25ms=maximum_delta,
                still_is_static=True,no_animated_key_blackouts=True,
                all_five_effects_bounded=True,zero_brightness_extinguishes=True,
                supplier_pin_mux=True,encoder_pins_preserved=True,blank_during_matrix_scan=True,
                hardware_row_timeout=True,key_scan_preserves_lighting_phase=True,suspend_extinguishes_rows=True,system_counter_untouched=True,
                brightness_duty_bounded=True,physical_color_order='not_observed')

def lighting_details_test():
    fw=Candidate();fw.initialize_app();replies=[]
    fw.callback('raw_hid_send',lambda args:replies.append(bytes(fw.cpu.mem_read(args[0],args[1]))) or 0)
    address=SCRATCH;fw.cpu.mem_write(address,b'F75Etest'+bytes(24))
    before=len(fw.writes);fw.call('raw_hid_receive',address,32)
    assert len(replies)==1 and replies[0][:8]==b'F75Ftest'
    assert replies[0][8:12]==bytes([0,28,35,0])
    assert len(replies[0])==32 and len(fw.writes)==before
    return dict(nonce_echo=True,requested_and_applied_effect=True,buffer_hash=True,peripheral_writes=False)

def gpio_modes_test():
    fw=Candidate();replies=[]
    fw.callback('raw_hid_send',lambda args:replies.append(bytes(fw.cpu.mem_read(args[0],args[1]))) or 0)
    addresses=[GPIO[0]+4,GPIO[1]+4,GPIO[2]+4,GPIO[3]+4,GPIO[0],GPIO[2]]
    values=[0x11,0x22,0x33,0x44,0x55,0x66]
    for address,value in zip(addresses,values):fw.word(address,value)
    pointer=SCRATCH;fw.cpu.mem_write(pointer,b'F75Mtest'+bytes(24));before=len(fw.writes)
    fw.call('raw_hid_receive',pointer,32)
    assert replies==[b'F75Ntest'+struct.pack('<6I',*values)] and len(fw.writes)==before
    return dict(fixed_registers_only=True,nonce_echo=True,peripheral_writes=False)

def pwm_hardware_snapshot_test():
    fw=Candidate();replies=[]
    fw.callback('raw_hid_send',lambda args:replies.append(bytes(fw.cpu.mem_read(args[0],args[1]))) or 0)
    fw.byte(SYMBOLS['duties'],37)
    for address in [0x40002030,0x40004024,0x40000020]:fw.word(address,37)
    fw.word(0x40000098,0xf0000f)
    pointer=SCRATCH;fw.cpu.mem_write(pointer,b'F75Xtest'+bytes(24));before=len(fw.writes)
    fw.call('raw_hid_receive',pointer,32)
    assert replies==[b'F75Ytest'+struct.pack('<6I',0,37,37,37,37,0xf0000f)]
    assert len(fw.writes)==before
    return dict(nonce_echo=True,intended_and_three_hardware_compare_values=True,no_gpio_or_timer_writes=True)

def timer1_register_contract_test():
    fw=Candidate();fw.call('f75_rgb_init')
    assert fw.word(0x40002014)==0, 'Timer1 key byte enabled match-reset actions'
    assert fw.word(0x40002018)==1<<8
    for w in fw.writes:
        address=w['address']
        if address in [0x40002014,0x40002018,0x40002098,0x400020a0] or 0x40002020<=address<=0x40002050:
            assert not w['value']&0xff000000,('unkeyed timer1 register got a key',w)
    fw=Candidate();replies=[]
    fw.callback('raw_hid_send',lambda args:replies.append(bytes(fw.cpu.mem_read(args[0],args[1]))) or 0)
    for address,value in zip([0x40000014,0x40002014,0x40004014,0x40000004,0x40002004,0x40004004],[1,2,3,4,5,6]):fw.word(address,value)
    pointer=SCRATCH;fw.cpu.mem_write(pointer,b'F75Ctest'+bytes(24));before=len(fw.writes)
    fw.call('raw_hid_receive',pointer,32)
    assert replies==[b'F75Dtest'+struct.pack('<6I',1,2,3,4,5,6)] and len(fw.writes)==before
    return dict(timer1_unkeyed_registers=True,no_unintended_match_resets=True,hardware_control_snapshot_readonly=True)

def spi_byte_boundaries_test():
    fw=Candidate();fw.word(GPIO[1],1<<8);fw.word(0x4001c000,0x40701)
    scan_mask=1<<19
    irq={'enabled':True}
    fw.word(0xe000e100,scan_mask)
    transfer={'reads':0,'pending':False,'stuck':False,'overflow':False};wire=[];selected=[]
    def write(cpu,access,address,size,value,data):
        if address==0xe000e180 and value&scan_mask:
            irq['enabled']=False;fw.word(0xe000e100,0)
        if address==0xe000e100 and value&scan_mask:irq['enabled']=True
        if address==0x4001c01c:
            assert not irq['enabled'], 'matrix IRQ can switch pins during selected byte'
            assert not fw.word(GPIO[1])&(1<<8), 'DATA written without CS'
            assert not transfer['pending'], 'previous frame not consumed'
            assert (fw.word(0x4001c000)>>8)&15==7
            wire.append(value);transfer.update(reads=0,pending=True)
        if address==GPIO[1]+0x24 and value&(1<<8):
            assert transfer['reads']>=6 or transfer['stuck'], 'CS released while clock busy'
            selected.append(value)
        if address==0x4001c018:
            assert value==4, 'per-byte clearing discarded a latched overflow'
    def read(cpu,access,address,size,value,data):
        if address==0x4001c00c:
            transfer['reads']+=1;n=transfer['reads']
            # Latched RIS is already set; FIFO/clock completion arrives later.
            fw.word(address,0x15 if transfer['stuck'] or n<3 else 0x11 if n<6 else 1)
        if address==0x4001c014:fw.word(address,5 if transfer['overflow'] else 4)
        if address==0x4001c01c:
            assert transfer['reads']>=6
            transfer['pending']=False
    fw.cpu.hook_add(UC_HOOK_MEM_WRITE,write);fw.cpu.hook_add(UC_HOOK_MEM_READ,read)
    pointer=SCRATCH;fw.cpu.mem_write(pointer,b'\x2a\x12\x34')
    assert fw.call('f75_panel_transfer',pointer,3)==1
    fw.cpu.mem_write(pointer,struct.pack('<2H',0xf800,0x07e0))
    assert fw.call('f75_panel_pixels',pointer,2)==1
    assert wire==[0x2a,0x12,0x34,0xf8,0,7,0xe0] and len(selected)==7
    assert irq['enabled'],'scan IRQ was not restored'
    transfer['overflow']=True
    assert fw.call('f75_panel_transfer',pointer,1)==0
    transfer.update(overflow=False,stuck=True)
    assert fw.call('f75_panel_transfer',pointer,1)==0
    assert fw.word(GPIO[1])&(1<<8)
    assert irq['enabled'],'timeout left scan IRQ disabled'
    irq['enabled']=False;fw.word(0xe000e100,0);transfer.update(stuck=False,pending=False)
    assert fw.call('f75_panel_transfer',pointer,1)==1
    assert not irq['enabled'],'transfer enabled an externally disabled scan IRQ'
    return dict(latched_irq_not_completion=True,waits_for_rx_and_idle=True,cs_per_byte=True,always_8bit=True,rgb565_order=True,overflow_stops_transfer=True,timeout_releases_cs=True,scan_deferred_during_byte=True,scan_enable_state_preserved=True)


def panel_bus_snapshot_test():
    fw=Candidate();replies=[]
    fw.callback('raw_hid_send',lambda args:replies.append(bytes(fw.cpu.mem_read(args[0],args[1]))) or 0)
    values=[1,2,3,4,5,6];fw.cpu.mem_write(SYMBOLS['bus'],struct.pack('<6I',*values))
    pointer=SCRATCH;fw.cpu.mem_write(pointer,b'F75Itest'+bytes(24));before=len(fw.writes)
    fw.call('raw_hid_receive',pointer,32)
    assert replies==[b'F75Jtest'+struct.pack('<6I',*values)] and len(fw.writes)==before
    return dict(nonce_echo=True,fixed_counters=True,peripheral_writes=False)


def isolation_actions_test():
    fw=Candidate();fw.initialize_app();fw.model_matrix=True;replies=[]
    fw.callback('raw_hid_send',lambda args:replies.append(bytes(fw.cpu.mem_read(args[0],args[1]))) or 0)
    pointer=SCRATCH
    def send(command,magic=b'F75DIAG!'):
        fw.cpu.mem_write(pointer,b'F75Ttest'+magic+command+bytes(12))
        fw.call('raw_hid_receive',pointer,32)
    before=len(fw.writes)
    send(b'RGB0',b'BADMAGIC');send(b'XXXX')
    assert not replies and len(fw.writes)==before
    before_config=bytes(fw.cpu.mem_read(SYMBOLS['state'],128))
    send(b'RGB0')
    assert replies[-1][:10]==b'F75Utest\1\0' and replies[-1][16:20]==b'RGB0'
    assert fw.call('f75_rgb_clock_active')==0 and fw.word(0x40006000)==0
    assert fw.word(0x400020a4)==0
    for base,mask in zip(GPIO,[0xb00,0x30,0x3c00,0x73f00]):assert fw.word(base)&mask==0
    fw.call('suspend_wakeup_init_user');assert fw.call('f75_rgb_clock_active')==0
    fw.pressed={(1,3)};fw.call('matrix_scan_custom',SCRATCH+0x20)
    assert fw.byte(SCRATCH+0x21)==8
    fw.pressed.clear();fw.call('matrix_scan_custom',SCRATCH+0x20)
    assert not any(fw.cpu.mem_read(SCRATCH+0x20,15))
    fw.callback('f75_panel_init',lambda args:1)
    fw.cpu.mem_write(SYMBOLS['tile_valid'],bytes([1])*16)
    send(b'LCD0');assert replies[-1][8:10]==b'\1\1'
    assert not any(fw.cpu.mem_read(SYMBOLS['tile_valid'],16))
    assert fw.call('f75_rgb_clock_active')==0
    assert bytes(fw.cpu.mem_read(SYMBOLS['state'],128))==before_config
    send(b'RGB1');assert replies[-1][8:10]==b'\0\1'
    assert fw.call('f75_rgb_clock_active')==1 and fw.word(0x400020a4)==0x7f0
    send(b'RGB2');assert replies[-1][8:11]==b'\0\1\1'
    assert fw.call('f75_rgb_clock_active')==1
    for _ in range(30):fw.call('begin_row')
    assert fw.word(0x40006000)==1 and fw.word(0x400020a4)==0
    for base in [0x40000000,0x40004000]:assert fw.word(base+0x98)&0xffffff==0
    for base,mask in zip(GPIO,[0xb00,0x30,0x3c00,0x73f00]):assert fw.word(base)&mask==0
    fw.call('suspend_wakeup_init_user');assert fw.word(0x400020a4)==0
    send(b'RGB1');assert fw.word(0x400020a4)==0x7f0
    return dict(scan_only_runs_irq_with_mux_disabled=True,rejected_unknown_actions=True,nonce_echo=True,led_timer_and_mux_disabled=True,typing_and_release_while_disabled=True,usb_wake_keeps_diagnostic_off=True,panel_reset_invalidates_cache=True,settings_preserved=True,reenable=True)


def radio_snapshot_test():
    fw=Candidate();fw.initialize_app();replies=[]
    fw.callback('raw_hid_send',lambda args:replies.append(bytes(fw.cpu.mem_read(args[0],args[1]))) or 0)
    address=SCRATCH;request=b'F75Ouart'+bytes(24)
    fw.cpu.mem_write(address,request);before=len(fw.writes)
    fw.call('raw_hid_receive',address,32)
    assert len(replies)==1 and replies[0][:8]==b'F75Zuart'
    flags,tx,rx,errors,event,status=struct.unpack_from('<6I',replies[0],8)
    assert (flags>>16)&255==0x11 and tx==rx==errors==event==0
    assert len(fw.writes)==before,'Read-only radio diagnostic changed MMIO'
    return dict(nonce_echo=True,fixed_counters=True,no_keycodes=True,peripheral_writes=False)


def main():
    usb_only = json.loads(IMAGE.with_suffix('.json').read_text()).get('profile') == 'usb_only'
    results = dict(candidate_sha256=hashlib.sha256(IMAGE.read_bytes()).hexdigest(),
                   matrix=matrix_test(), keys=key_test(),radio_snapshot=radio_snapshot_test(), pwm_hardware_snapshot='omitted' if usb_only else pwm_hardware_snapshot_test(), gpio_modes=gpio_modes_test(), lighting_details='omitted' if usb_only else lighting_details_test(), rgb='omitted' if usb_only else rgb_test(), panel='omitted in USB-only profile' if usb_only else panel_test(), boot_shortcut=boot_shortcut_test(), health=health_test(), startup_guard='omitted in USB-only profile' if usb_only else startup_guard_test(), reset_recovery=reset_recovery_test(), clock_divider=clock_divider_test(),
                   timer1_register_contract='omitted' if usb_only else timer1_register_contract_test(),spi_byte_boundaries='omitted' if usb_only else spi_byte_boundaries_test(),panel_bus='omitted' if usb_only else panel_bus_snapshot_test(),isolation_actions='omitted' if usb_only else isolation_actions_test(),gpio_snapshot=gpio_snapshot_test(), auxiliary_snapshot=auxiliary_snapshot_test(), wheel_matrix=wheel_matrix_button_test(), performance=performance_snapshot_test(), hardware_tested=False, usb_reports_sent=False)
    path = Path(os.environ.get('F75_TEST_RECEIPT', ROOT / 'analysis/keyboard-image-tests.json'))
    path.write_text(json.dumps(results, indent=2) + '\n')
    print(json.dumps(results, indent=2))


if __name__ == '__main__':
    main()
