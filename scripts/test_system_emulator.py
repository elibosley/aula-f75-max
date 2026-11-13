#!/usr/bin/env python3
"""End-to-end tests of the linked ARM image on the wired QEMU model."""
import argparse
import hashlib
import json
from pathlib import Path
import struct

from system_emulator import System, ROOT, USB, HOST, QEMU


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def enumerate_usb(machine):
    machine.pump()
    machine.pump(1 << 31)
    device = machine.control(0x80, 6, 0x100, length=18)
    assert device == bytes.fromhex('1201000200000040edfe50f7010001020301'), device.hex()
    machine.control(0, 5, 7)
    assert machine.read32(USB + 12) == 7
    header = machine.control(0x80, 6, 0x200, length=9)
    config = machine.control(0x80, 6, 0x200, length=int.from_bytes(header[2:4], 'little'))
    assert len(config) == 91 and config[4] == 3, config.hex()
    interfaces, endpoints, report_lengths = [], [], {}
    interface=0
    i = 0
    while i < len(config):
        length, kind = config[i:i+2]
        assert length >= 2
        if kind == 4: interface=config[i+2];interfaces.append(interface)
        if kind == 0x21:report_lengths[interface]=int.from_bytes(config[i+7:i+9],'little')
        if kind == 5: endpoints.append(config[i+2])
        i += length
    assert interfaces == [0, 1, 2] and endpoints == [0x81, 0x82, 3, 0x84]
    # Exercise all three HID report descriptors through the real EP0 stack.
    reports = []
    assert report_lengths[0]==68 and report_lengths[1]==34 and report_lengths[2]>=52
    for interface, length in sorted(report_lengths.items()):
        descriptor = machine.control(0x81, 6, 0x2200, index=interface, length=length)
        assert len(descriptor) == length
        reports.append(hashlib.sha256(descriptor).hexdigest())
    machine.control(0, 9, 1)
    machine.advance(100)
    machine.pump()
    return dict(device=device.hex(), configuration=config.hex(), report_descriptor_sha256=reports,
                usb_address=7, configured=True, transport='modeled bus tokens and endpoint RAM; real USB ISR/driver')


def health(machine, nonce=b'test'):
    machine.endpoint_out(3, b'F75?' + nonce + bytes(24))
    machine.advance(20)
    machine.pump()
    data = machine.endpoint_in(2)
    assert data and len(data) == 32 and data[:8] == b'F75!' + nonce, data
    uptime, scans, frames, epoch = struct.unpack_from('<IIII', data, 8)
    return dict(uptime_ms=uptime, matrix_scans=scans, complete_frames=frames,
                release_epoch=epoch, flags=data[24], page=data[25], caps_swap=data[29], os=data[30])


def auxiliary_switches(machine):
    machine.write32(HOST + 0x100 + 14 * 4, 1)
    machine.write32(HOST + 0x100 + 1 * 4, 1 << 3)
    machine.advance(100); machine.pump()
    machine.endpoint_out(3, b'F75Kaux!' + bytes(24))
    machine.advance(20); machine.pump()
    data = machine.endpoint_in(2)
    assert data == b'F75Laux!' + bytes(14) + bytes([1, 0, 1]) + bytes(7), data
    machine.write32(HOST + 0x100 + 14 * 4, 0)
    machine.write32(HOST + 0x100 + 1 * 4, 0)
    machine.advance(100); machine.pump()
    machine.endpoint_in(1)
    return dict(real_matrix_scan=True, unassigned_position_visible=True, typing_key_masked=True)


def keys(machine):
    mac=health(machine,b'kmap')['os']==0
    machine.endpoint_in(1)
    result = []
    for row, col, expected in [(1, 3, bytes([0,0,4,0,0,0,0,0])),
                               (0, 3, bytes([8 if mac else 1,0,0,0,0,0,0,0])),
                               (0, 5, bytes([0,0,0x39,0,0,0,0,0])),
                               (2, 5, bytes([8 if mac else 4,0,0,0,0,0,0,0]))]:
        machine.write32(HOST + 0x100 + row * 4, 1 << col)
        machine.advance(15); machine.pump()
        actual = machine.endpoint_in(1)
        assert actual == expected, (row, col, actual, expected)
        machine.write32(HOST + 0x100 + row * 4, 0)
        machine.advance(15); machine.pump()
        assert machine.endpoint_in(1) == bytes(8)
        result.append(dict(row=row, col=col, down=actual.hex(), released=True))
    return result


def typing_during_animation(machine):
    machine.endpoint_in(1)
    for delay in [1,3,5,7,11,13,17,19]:
        machine.write32(HOST + 0x30, 0)
        machine.advance(delay); machine.pump()
        machine.write32(HOST + 0x100 + 1 * 4, 1 << 3)
        machine.advance(15); machine.pump()
        assert machine.endpoint_in(1) == bytes([0,0,4,0,0,0,0,0]), ('missed typing pulse', delay)
        machine.write32(HOST + 0x100 + 1 * 4, 0)
        machine.advance(15); machine.pump()
        assert machine.endpoint_in(1) == bytes(8), ('missed release', delay)
    return dict(pulses=8, pulse_ms=15, different_frame_phases=True, all_presses_and_releases_received=True)


def wheel_and_profiles(machine):
    def move_time(ms):
        machine.write32(HOST + 0x30, 0)
        machine.advance(ms); machine.pump()
    def clear_reports():
        for ep in [1, 4]: machine.endpoint_in(ep)
    def press_button(ms=60):
        machine.write32(HOST + 0x100 + 14 * 4, 1); move_time(max(ms, 100))
        machine.write32(HOST + 0x100 + 14 * 4, 0); move_time(100)
    def turn(reverse=False):
        for state in ([3, 1, 0, 2, 3] if reverse else [3, 2, 0, 1, 3]):
            machine.write32(HOST + 0x200, (1 << 10) | ((state & 1) << 2) | ((state & 2) << 2))
            move_time(5)
    press_button()
    nav = machine.symbols['navigation']
    assert machine.read(nav, 2) == bytes([1, 0])
    turn(); assert machine.read(nav, 2) == bytes([1, 1]), 'first detent did not move'
    turn(); assert machine.read(nav, 2) == bytes([1, 2]), 'second detent failed to move'
    turn(True); assert machine.read(nav, 2) == bytes([1, 1]), 'reversal did not move immediately'
    press_button(720)
    assert machine.read(nav, 1) == bytes([0])
    clear_reports()
    # Change OS through the actual Fn+M matrix chord, then verify USB modifiers.
    machine.write32(HOST + 0x100 + 11 * 4, 1 << 5); move_time(20)
    machine.write32(HOST + 0x100 + 8 * 4, 1 << 4); move_time(20)
    machine.write32(HOST + 0x100 + 8 * 4, 0)
    machine.write32(HOST + 0x100 + 11 * 4, 0); move_time(20)
    clear_reports()
    assert health(machine, b'win!')['os'] == 1
    for row, col, modifier in [(2, 5, 4), (0, 3, 1)]:
        machine.write32(HOST + 0x100 + row * 4, 1 << col); move_time(20)
        assert machine.endpoint_in(1) == bytes([modifier, 0, 0, 0, 0, 0, 0, 0])
        machine.write32(HOST + 0x100 + row * 4, 0); move_time(20)
        assert machine.endpoint_in(1) == bytes(8)
    return dict(one_detent_per_item=True, immediate_reversal=True, button_press_opens_menu=True,
                hold_returns_home=True, fn_m_changes_os=True,
                windows_alt_report=True, caps_ctrl_swap_preserved_on_windows=True)


def rgb_runtime(machine):
    assert machine.read32(0x40002014)==0, 'Timer1 match-control has unwanted reset/action bits'
    def read(nonce):
        machine.endpoint_out(3,b'F75R'+nonce+bytes(24))
        machine.advance(10);machine.pump()
        data=machine.endpoint_in(2)
        assert data[:8]==b'F75S'+nonce
        return struct.unpack_from('<6I',data,8)
    machine.endpoint_out(3,b'F75Econf'+bytes(24));machine.advance(10);machine.pump()
    detail=machine.endpoint_in(2)
    assert detail[:8]==b'F75Fconf' and detail[8:12]==bytes([0,28,35,0])
    assert struct.unpack_from('<I',detail,12)[0]==0
    machine.endpoint_out(3,b'F75Xpwm!'+bytes(24));machine.advance(10);machine.pump()
    pwm_reply=machine.endpoint_in(2);assert pwm_reply[:8]==b'F75Ypwm!'
    pwm=struct.unpack_from('<6I',pwm_reply,8)
    assert 0<=pwm[0]<18 and pwm[1]>0 and pwm[2]==pwm[3]==pwm[4]==pwm[1],pwm
    first=read(b'rgb1')
    machine.write32(HOST+0x30,0);machine.advance(100);machine.pump()
    second=read(b'rgb2')
    assert first[0]==second[0]==1
    assert second[1]>first[1] and second[2]==first[2]==0 and second[3]>first[3],(first,second)
    assert second[4]==28 and 0<=second[5]<18
    # Every matrix sample is taken with the shared PWM pin mux disabled.
    machine.until('f75_matrix_sample')
    irq_before=machine.read32(machine.symbols['irq_count'])
    assert machine.read32(0x400020a4)==0
    assert machine.read32(0x40000098)&0xf00000==0
    assert machine.read32(0x40004098)&0xf00000==0
    machine.until('housekeeping_task_user')
    assert machine.read32(0x400020a4)==0x7f0
    assert machine.read32(0x40044004)&0xf0==0 and machine.read32(0x40048004)&0x43ff==0
    assert machine.read32(0x40044004)&0x6000==0x6000
    if 'f75_battery_task' in machine.symbols:
        # Gauge SDA A15 is released as an input between reads; A13 CS and
        # A14 clock retain their stock output directions.
        assert not machine.read32(0x40044004)&0x8000
    else:assert machine.read32(0x40044004)&0x8000
    assert machine.read32(0x40046004)&0x40003==0x40003
    assert machine.read32(0x40008008)==255, 'RTOS clock rate changed'
    return dict(first=first,second=second,row_irq_advances=True,animation_buffers_advance=True,
                pwm_disabled_during_key_sense=True,lighting_clock_advances_during_key_scan=True,key_sampling_owned_by_row_irq=True,rtos_timer4_free_running=True,
                optical_output='requires physical check',model='registers and row IRQ; not LED electrical behavior')

def panel_trace(machine, destination):
    count = machine.read32(HOST + 4)
    assert count < 2097152, 'SPI capture overflow'
    trace = machine.read(0x60000000, count * 2)
    segments = []
    for value, dc in zip(trace[::2], trace[1::2]):
        if not dc:
            segments.append([value, bytearray()])
        else:
            assert segments, 'data before command'
            segments[-1][1].append(value)
    board = json.loads((ROOT / 'firmware/targets/f75max/board-map.json').read_text())
    expected = [(int(c['command'], 16), bytes(c['data'])) for c in board['display']['init_commands']]
    actual = [(c, bytes(data)) for c, data in segments[:len(expected)]]
    assert actual == expected, ('panel initialization differs from recovered stock commands', actual)
    from PIL import Image
    image = Image.new('RGB', (128, 128))
    columns = rows = None
    tiles = 0
    updates=segments[len(expected):]
    for segment,(command,data) in enumerate(updates):
        last=segment==len(updates)-1
        if command == 0x2a:
            if last and len(data)<4: break
            assert len(data) == 4
            columns = struct.unpack('>HH', data)
        elif command == 0x2b:
            if last and len(data)<4: break
            assert len(data) == 4
            rows = struct.unpack('>HH', data)
        elif command == 0x2c:
            assert columns == (2, 129) and rows and 1 <= rows[0] <= rows[1] <= 128
            width, height = columns[1] - columns[0] + 1, rows[1] - rows[0] + 1
            if last and len(data)<width*height*2: break
            assert len(data) == width * height * 2, ('extra/missing display bytes', len(data), width, height)
            for index, (rgb,) in enumerate(struct.iter_unpack('>H', data)):
                image.putpixel((index % width, rows[0] - 1 + index // width),
                               (((rgb >> 11) & 31) * 255 // 31, ((rgb >> 5) & 63) * 255 // 63, (rgb & 31) * 255 // 31))
            tiles += 1
    assert tiles >= 16 and len(set(image.get_flattened_data())) > 10
    image.save(destination)
    return dict(spi_bytes=count, complete_tiles=tiles, screenshot=str(destination.relative_to(ROOT)),
                screenshot_sha256=sha(destination), initialization_matches_stock=True, exact_pixel_lengths=True)


def isolation_actions(machine):
    def send(command):
        machine.endpoint_out(3,b'F75Tisol'+b'F75DIAG!'+command+bytes(12))
        machine.advance(800 if command==b'LCD0' else 30);machine.pump()
        data=machine.endpoint_in(2)
        assert data and data[:8]==b'F75Uisol' and data[16:20]==command,data
        return data
    page=health(machine,b'isol')['page']
    data=send(b'RGB0');assert data[8:10]==b'\1\1'
    assert machine.read32(0x40006000)==0 and machine.read32(0x400020a4)==0
    count=machine.read32(machine.symbols['irq_count'])
    off_keys=keys(machine)
    assert machine.read32(machine.symbols['irq_count'])==count
    machine.write32(HOST+0x30,0)
    data=send(b'LCD0');assert data[8:10]==b'\1\1'
    machine.advance(100);machine.pump()
    assert machine.read32(HOST+4)>0
    assert health(machine,b'rset')['page']==page
    assert machine.read32(machine.symbols['irq_count'])==count
    data=send(b'RGB1');assert data[8:10]==b'\0\1'
    machine.advance(30);machine.pump()
    assert machine.read32(machine.symbols['irq_count'])>count
    data=send(b'RGB2');assert data[8:11]==b'\0\1\1'
    count=machine.read32(machine.symbols['irq_count'])
    scan_keys=keys(machine)
    assert machine.read32(machine.symbols['irq_count'])>count
    assert machine.read32(0x40006000)==1 and machine.read32(0x400020a4)==0
    for base in [0x40000000,0x40004000]:assert machine.read32(base+0x98)==0
    data=send(b'RGB1');assert data[8:11]==b'\0\1\0'
    return dict(scan_only_has_live_irq_no_pwm_mux=True,scan_only_typing=scan_keys,real_usb_commands=True,typing_with_led_timer_off=off_keys,screen_reset_and_redraw=True,page_preserved=True,reenable=True)


def recovery(image):
    results = []
    for held, magic in [(False, False), (True, False), (False, True), (True, True)]:
        with System(image, held=held, magic=magic) as machine:
            destination = 0x1fff0300 if held or magic else machine.symbols['_crt0_entry']
            machine.until(destination)
            if held or magic:
                assert machine.read32(0x20007ffc) == 0
                assert machine.read32(0x40060024) == 0
                assert bytes.fromhex(machine.packet('pD')) == struct.pack('<I', 0x20000348)
                assert machine.read(0x20000000, 0x348) == bytes(0x348)
                assert machine.read(0x20000348, 0x7ff8-0x348) == b'\xa5' * (0x7ff8-0x348)
                assert machine.read32(0x20007ff8) == 0x52543546
            else:
                assert machine.read(0x20000000, 0x7ffc) == b'\xa5' * 0x7ffc
            assert machine.read32(HOST + 8) == 0
            results.append(dict(wheel_held=held, magic=magic,
                                reached='rom_boundary' if held or magic else 'c_runtime'))
    isolated = []
    for row in [0, 13]:
        with System(image) as machine:
            machine.write32(HOST + 0x100 + row * 4, 1)
            machine.until('_crt0_entry')
            assert machine.read32(0x40048000) & 0x43ff == 0
            isolated.append(row)
    return dict(cases=results, factory_rom_executed=False, physical_wheel_entry_verified=False,
                same_column_other_rows_do_not_enter_rom=isolated)


def clock_states(image):
    states = []
    for value in range(16):
        with System(image, ahbcp=value) as machine:
            machine.until('main')
            states.append(value)
            assert machine.read32(HOST + 8) == 0
    return dict(valid_handoff_values_reach_main=states, actual_board_handoff='not_measured')


def factory_loader(image):
    cases = []
    for held, magic in [(True, False), (False, True)]:
        with System(image, held=held, magic=magic, factory_rom=True) as machine:
            machine.poll_checkpoint = 0x1fff03bc
            machine.pump(); machine.pump(1 << 31)
            descriptor = machine.control(0x80, 6, 0x100, length=18)
            assert descriptor == bytes.fromhex('1201000200000040450c4071010100000001')
            machine.control(0, 5, 7)
            assert machine.read32(USB + 12) == 7
            machine.control(0, 9, 1)
            machine.control_out(0x21, 9, struct.pack('<I', 0x55aa01) + bytes(60), value=0x300)
            reply = machine.control(0xa1, 1, value=0x300, length=64)
            assert reply[:8] == bytes.fromhex('01aa5500fafafafa'), reply.hex()
            assert reply[8:10] == bytes([32, 5]), reply.hex()
            assert machine.read32(HOST + 8) == 0
            # Exit the real ROM while the same button remains held. The reset
            # guard must consume its return marker instead of looping in ISP.
            machine.write(USB + 0x100, struct.pack('<BBHHH', 0x21, 9, 0x300, 0, 64))
            machine.pump(1 << 23)
            machine.write(USB + 0x100, struct.pack('<I', 0x55aa07) + bytes(60))
            machine.write32(USB + 0x18, 0x80000040)
            machine.pump(1 << 21)
            machine.write32(USB + 0x18, 0x80000000)
            machine.event(1 << 22)
            machine.until('main')
            assert machine.read32(0x20007ff8) == 0
            cases.append(dict(wheel_held=held, software_magic=magic, descriptor=descriptor.hex(), rom_identity_reply=reply.hex()))
    return dict(status='passed', actual_factory_rom_executed=True,
                rom_sha256='06508333749a88ac1251497563015e4709606842e3c0ad304cdcf2eb7951077c',
                chip_id_register='inferred 0x3258 for ROM family 32 chip 5', cases=cases)


def hardfault_loader(image):
    results = []
    for runtime in [False, True]:
        with System(image, factory_rom=True) as machine:
            if runtime:
                machine.until('main')
            assert machine.packet('M3d000,2:00de') == 'OK'  # actual UDF instruction
            assert machine.packet('Pf=' + struct.pack('<I', 0x3d001).hex()) == 'OK'
            machine.poll_checkpoint = 0x1fff03bc
            machine.pump()
            fault = struct.unpack('<12I', machine.read(0x20007e00, 48))
            assert fault[0] == 0x46373546 and fault[10] == 0x3d000
            assert fault[2] == (0xfffffffd if runtime else 0xfffffff9)
            machine.pump(1 << 31)
            descriptor = machine.control(0x80, 6, 0x100, length=18)
            assert descriptor == bytes.fromhex('1201000200000040450c4071010100000001')
            results.append(dict(runtime_psp=runtime, fault_pc=hex(fault[10]),
                                exception_return=hex(fault[2]), real_factory_usb_enumerated=True))
    return dict(status='passed', injected_undefined_instruction=True, cases=results)


def baseline_failures():
    broken = ROOT / 'analysis/flashed/c4d5d61510ec4b5490a1684a355702a7/f75max-wired-test.bin'
    assert sha(broken) == '92ec232597e9b8f19a9c4fd71634f6e53c97a6a67d45b9d4b37cc9b5c6a65c95'
    with System(broken, ahbcp=8) as machine:
        machine.until('HardFault_Handler')
        clock = dict(image_sha256=sha(broken), ahbcp=8, reached='HardFault_Handler', before_main=True)
    old_spi = ROOT / 'analysis/candidates/725e0e0eae0f17261497674d74122ee6b77f205bcd9a0164a85a07486bab68da/f75max-wired-test.bin'
    with System(old_spi) as machine:
        machine.until('f75_panel_init')
        # This old, deliberately broken image sleeps inside panel startup.
        # Waiting for its return can stop in WFI without advancing the model's
        # host deadline. Drive a bounded 300 ms of virtual time and stop once
        # the excessive SPI tail is observed; a broken image need not return.
        count = 0
        for _ in range(30):
            machine.advance(10)
            count = machine.read32(HOST + 4)
            if count > 1000: break
        assert count > 1000, ('upstream SPI regression no longer reproduced', count)
        spi = dict(image_sha256=sha(old_spi), init_bytes=count, unexpected_transfer_tail=True,
                   virtual_time_driven=True, requested_time_bound_ms=300)
    return dict(clock_divide_by_zero=clock, spi_master_tail=spi)


def faults(image, full_ui):
    result = {}
    with System(image) as machine:
        machine.write32(HOST + 0x28, 1)
        machine.advance(100)
        pc = machine.pc()
        begin = machine.symbols['SystemInit']
        assert begin <= pc < begin + 400, hex(pc)
        result['pll_not_ready'] = dict(detected_stall_pc=hex(pc), automatic_recovery=False)
    # Early recovery must not depend on PLL readiness.
    with System(image, held=True) as machine:
        machine.write32(HOST + 0x28, 1)
        machine.until(0x1fff0300)
        result['wheel_with_pll_not_ready'] = 'rom_boundary'
    if full_ui:
        with System(image) as machine:
            machine.write32(HOST + 0x24, 1)
            machine.until('f75_panel_init')
            machine.until(0x1fff0300)
            elapsed = machine.read32(HOST + 12)
            assert 1900000 <= elapsed <= 2400000, elapsed
            result['spi_no_completion'] = dict(reached='rom_boundary', elapsed_us=elapsed,
                                               reset_magic_caught_by_early_guard=True)
        with System(image) as machine:
            if full_ui and 'f75_panel_transfer' in machine.symbols:
                enumerate_usb(machine)
                # This case injects a failure after a completed frame. Smaller
                # slices need more main-loop iterations in the instruction-time
                # model; startup timeout behavior is checked separately above.
                machine.advance(250); machine.pump()
                before = health(machine, b'prev')
                assert before['complete_frames'] > 0
                machine.write32(HOST + 0x24, 1)
                machine.write32(HOST + 0x30, 0)
                # Trigger a visible change so cached, unchanged tiles cannot
                # postpone the deliberately broken transfer indefinitely.
                machine.write32(HOST + 0x100 + 14 * 4, 1)
                machine.advance(100); machine.pump()
                machine.write32(HOST + 0x100 + 14 * 4, 0)
                machine.advance(100); machine.pump()
                after = health(machine, b'fail')
                assert after['matrix_scans'] > before['matrix_scans']
                assert not after['flags'] & 1
                assert machine.read32(0x40046000) & (1 << 8)
                assert machine.read32(0x4001c010) == 0
                result['spi_runtime_timeout'] = dict(usb_still_responding=True, matrix_still_scanning=True,
                                                     display_marked_unavailable=True, chip_select_released=True)
    return result


def run(image, output, baselines=True, private_evidence=True):
    image = Path(image).resolve()
    output = Path(output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    profile = json.loads(image.with_suffix('.json').read_text())['profile']
    full_ui = profile == 'full_ui'
    result = dict(status='running', candidate_sha256=sha(image), elf_sha256=sha(image.with_suffix('.elf')),
                  emulator_sha256=sha(QEMU), model_sha256=sha(ROOT / 'emulator/qemu/f75max.c'),
                  profile=profile, hardware_writes=False, function_stubs=[],
                  scope='Actual ARM reset/startup/ChibiOS/NVIC/SysTick/USB/matrix/SPI; modeled peripheral electronics',
                  limitations=[('Captured factory ROM is exercised in recovery cases; chip-ID metadata is inferred' if private_evidence else 'Factory ROM replay is not part of this source-only run'), 'No physical pin, oscillator, panel or USB PHY verification',
                               'Instruction-time model is not cycle-accurate', 'No wireless/battery model; RGB row IRQ and timer registers only'])
    try:
        result['reset_recovery'] = recovery(image)
        result['clock_states'] = clock_states(image)
        if private_evidence:result['factory_loader'] = factory_loader(image)
        else:result['factory_loader'] = dict(status='not_run',required=False,reason='Private factory ROM capture is not part of public source verification')
        if private_evidence and 'hardfault_entry' in json.loads(image.with_suffix('.json').read_text())['reset_recovery']:
            result['hardfault_loader'] = hardfault_loader(image)
        if baselines:
            result['historical_failures'] = baseline_failures()
        result['fault_injection'] = faults(image, full_ui)
        if full_ui:
            # Keep the pixel proof separate from long interaction tests. Faster
            # firmware can fill the bounded trace during those tests; drain it
            # while testing input rather than silently truncating display data.
            with System(image) as panel_machine:
                enumerate_usb(panel_machine)
                panel_machine.advance(100); panel_machine.pump()
                result['panel'] = panel_trace(panel_machine, output.with_suffix('.png'))
        with System(image) as machine:
            result['usb'] = enumerate_usb(machine)
            result['first_health'] = health(machine)
            machine.write32(HOST + 0x30, 0)
            result['keyboard_reports'] = keys(machine)
            if 'f75_panel_transfer' in machine.symbols:
                result['typing_during_animation'] = typing_during_animation(machine)
            result['wheel_and_profiles'] = wheel_and_profiles(machine)
            if full_ui and 'f75_rgb_init' in machine.symbols: result['rgb'] = rgb_runtime(machine)
            result['auxiliary_switches'] = auxiliary_switches(machine)
            if full_ui and 'tile_signatures' in machine.symbols:
                # Auxiliary-switch test leaves the real UI on its static menu.
                # Let the startup notice and spring settle before checking that
                # unchanged pixels need no SPI writes, then select a new page.
                machine.advance(500); machine.pump()
                initial=health(machine,b'cach')
                assert initial['page']==1
                expected_page=2+machine.read(machine.symbols['navigation']+1,1)[0]
                machine.write32(HOST+0x30,0)
                machine.advance(100); machine.pump()
                stable=health(machine,b'same')
                assert stable['complete_frames']>initial['complete_frames']
                assert machine.read32(HOST+4)==0, 'unchanged menu was retransmitted'
                machine.write32(HOST+0x100+14*4,1);machine.advance(100);machine.pump()
                machine.write32(HOST+0x100+14*4,0);machine.advance(100);machine.pump()
                changed=health(machine,b'move')
                assert changed['page']==expected_page and machine.read32(HOST+4)>0
                result['screen_cache']=dict(static_menu_avoids_spi=True,new_page_updates_pixels=True,frames_still_advance=True)
                original_page=changed['page']
                machine.endpoint_out(3,b'F75Aanim'+b'DRAWTEST'+bytes(16))
                machine.advance(20);machine.pump()
                assert machine.endpoint_in(2)==b'F75Aanim'+b'DRAWTEST'+bytes(16)
                machine.write32(HOST+0x30,0);machine.advance(100);machine.pump()
                assert machine.read(machine.symbols['frame']+16,11)==b'Timing test'
                assert machine.read32(HOST+4)>0
                for _ in range(51):
                    machine.write32(HOST+0x30,0);machine.advance(100);machine.pump()
                assert machine.read(machine.symbols['frame']+16,11)!=b'Timing test'
                assert health(machine,b'done')['page']==original_page
                result['visual_benchmark']=dict(animation_updates_real_spi=True,expires_after_five_seconds=True,page_preserved=True)
            machine.advance(100); machine.pump()
            result['second_health'] = health(machine, b'next')
            first, second = result['first_health'], result['second_health']
            assert second['uptime_ms'] > first['uptime_ms'] and second['matrix_scans'] > first['matrix_scans']
            assert second['flags'] & 10 == 10
            if full_ui:
                assert second['complete_frames'] > first['complete_frames'] and second['flags'] & 1
            else:
                assert second['complete_frames'] == 0 and not second['flags'] & 1
                assert machine.read32(HOST + 4) == 0
            if full_ui:result['isolation_actions']=isolation_actions(machine)
            if full_ui and 'f75_panel_bus' in machine.symbols:
                machine.endpoint_out(3,b'F75Ibus!'+bytes(24));machine.advance(30);machine.pump()
                data=machine.endpoint_in(2);assert data[:8]==b'F75Jbus!'
                counters=struct.unpack_from('<6I',data,8)
                assert counters[0]>0 and counters[1]==counters[2]==0,counters
                assert machine.read32(HOST+0x34)==0, 'CS/DC changed or format reset while SPI busy'
                assert machine.read32(HOST+0x38)>0 and machine.read32(HOST+0x3c)==0
                result['spi_byte_boundaries']=dict(counters=counters,wire_violations=0,frames8=machine.read32(HOST+0x38),frames16=0)
            assert machine.read32(HOST + 8) == 0, 'unmodeled MMIO was accessed'
            result['unmodeled_mmio_accesses'] = 0
        result['status'] = 'passed'
    except Exception as error:
        result['status'] = 'failed'
        result['error'] = f'{type(error).__name__}: {error}'
        raise
    finally:
        output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(dict(status=result['status'], profile=profile, candidate_sha256=result['candidate_sha256'], receipt=str(output)), indent=2))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('image', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--skip-baselines', action='store_true')
    parser.add_argument('--source-only', action='store_true', help='Verify public sources without private ROM or historical firmware captures')
    args = parser.parse_args()
    run(args.image, args.output, not (args.skip_baselines or args.source_only), not args.source_only)
