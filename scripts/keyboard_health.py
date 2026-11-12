#!/usr/bin/env python3
"""Read the wired test image's counters, or explicitly request its ROM entry."""
import argparse
import json
import secrets
import struct
import time

import hid
from keyboard_transport_lock import TransportLock


def exchange(boot=False):
    devices = [d for d in hid.enumerate(0xfeed, 0xf750) if d['usage_page'] == 0xff60]
    if len(devices) != 1:
        raise RuntimeError('Exactly one F75 wired-test diagnostics interface must be present')
    nonce = secrets.token_bytes(4)
    request = b'F75B' + nonce + bytes.fromhex('aa42895aff7162cc') + bytes(16) if boot else b'F75?' + nonce + bytes(24)
    with TransportLock(), hid.Device(path=devices[0]['path']) as device:
        count = device.write(b'\0' + request)
        if count not in (32, 33):
            raise RuntimeError('Short diagnostics request')
        response = bytes(device.read(32, 1000))
    if len(response) != 32 or response[:4] != (b'F75B' if boot else b'F75!') or response[4:8] != nonce:
        raise RuntimeError('Diagnostics reply or nonce did not verify')
    if boot:
        return {'boot_request_acknowledged': True}
    uptime, scans, frames, epoch = struct.unpack_from('<IIII', response, 8)
    flags = response[24]
    return dict(uptime_ms=uptime, matrix_scans=scans, complete_frames=frames, release_epoch=epoch,
                panel_ready=bool(flags & 1), usb_selected=bool(flags & 2), control=bool(flags & 4),
                matrix_ready=bool(flags & 8), page=response[25], protocol=response[28],
                wheel_gpio_high=bool(response[26] & 1), selector_gpio_bits=response[26] >> 1,
                encoder_gpio_bits=response[27],
                caps_swap=bool(response[29]), os=['Mac','Windows','Android'][response[30]] if response[30]<3 else 'Unknown',
                wheel_pressed=bool(response[31]),route_memory_supported=bool(flags&32),fast_settings_supported=bool(flags&64))


def gpio_snapshot():
    devices = [d for d in hid.enumerate(0xfeed, 0xf750) if d['usage_page'] == 0xff60]
    if len(devices) != 1:
        raise RuntimeError('Exactly one wired diagnostics interface must be present')
    nonce = secrets.token_bytes(4)
    with TransportLock(), hid.Device(path=devices[0]['path']) as device:
        device.write(b'\0F75G' + nonce + bytes(24))
        response = bytes(device.read(32, 1000))
    if len(response) != 32 or response[:8] != b'F75H' + nonce:
        raise RuntimeError('GPIO snapshot or nonce did not verify')
    return dict(zip(['GPIOA_DATA','GPIOB_DATA','GPIOC_DATA','GPIOD_DATA','GPIOB_MODE','GPIOB_CFG1'],
                    [f'{x:08x}' for x in struct.unpack_from('<6I',response,8)]))


def mode_snapshot():
    devices=[d for d in hid.enumerate(0xfeed,0xf750) if d['usage_page']==0xff60]
    if len(devices)!=1:raise RuntimeError('Exactly one wired diagnostics interface must be present')
    nonce=secrets.token_bytes(4)
    with TransportLock(), hid.Device(path=devices[0]['path']) as device:
        device.write(b'\0F75M'+nonce+bytes(24));response=bytes(device.read(32,1000))
    if len(response)!=32 or response[:8]!=b'F75N'+nonce:raise RuntimeError('GPIO mode snapshot or nonce did not verify')
    return dict(zip(['GPIOA_MODE','GPIOB_MODE','GPIOC_MODE','GPIOD_MODE','GPIOA_DATA','GPIOC_DATA'],[f'{v:08x}' for v in struct.unpack_from('<6I',response,8)]))

def auxiliary_snapshot():
    devices = [d for d in hid.enumerate(0xfeed, 0xf750) if d['usage_page'] == 0xff60]
    if len(devices) != 1:
        raise RuntimeError('Exactly one wired diagnostics interface must be present')
    nonce = secrets.token_bytes(4)
    with TransportLock(), hid.Device(path=devices[0]['path']) as device:
        device.write(b'\0F75K' + nonce + bytes(24))
        response = bytes(device.read(32, 1000))
    if len(response) != 32 or response[:8] != b'F75L' + nonce:
        raise RuntimeError('Auxiliary switch snapshot or nonce did not verify')
    active = [(row, col) for row, bits in enumerate(response[8:23]) for col in range(6) if bits & (1 << col)]
    return dict(unassigned_positions=active, wheel_gpio_high=bool(response[23]), wheel_pressed=bool(response[24]))


def performance_snapshot():
    devices = [d for d in hid.enumerate(0xfeed, 0xf750) if d['usage_page'] == 0xff60]
    if len(devices) != 1:
        raise RuntimeError('Exactly one wired diagnostics interface must be present')
    nonce = secrets.token_bytes(4)
    with TransportLock(), hid.Device(path=devices[0]['path']) as device:
        device.write(b'\0F75P' + nonce + bytes(24))
        response = bytes(device.read(32, 1000))
    if len(response) != 32 or response[:8] != b'F75Q' + nonce:
        raise RuntimeError('Performance snapshot or nonce did not verify')
    names = ['tiles','render_ticks','spi_ticks','max_render_ticks','max_spi_ticks','max_scan_gap_ticks']
    return dict(zip(names, struct.unpack_from('<6I',response,8)))


def rgb_snapshot():
    devices=[d for d in hid.enumerate(0xfeed,0xf750) if d['usage_page']==0xff60]
    if len(devices)!=1: raise RuntimeError('Exactly one wired diagnostics interface must be present')
    nonce=secrets.token_bytes(4)
    with TransportLock(), hid.Device(path=devices[0]['path']) as device:
        device.write(b'\0F75R'+nonce+bytes(24));response=bytes(device.read(32,1000))
    if len(response)!=32 or response[:8]!=b'F75S'+nonce: raise RuntimeError('RGB snapshot or nonce did not verify')
    return dict(zip(['flags','row_interrupts','scan_pauses','color_frames','brightness','row'],struct.unpack_from('<6I',response,8)))

def lighting_snapshot():
    devices=[d for d in hid.enumerate(0xfeed,0xf750) if d['usage_page']==0xff60]
    if len(devices)!=1:raise RuntimeError('Exactly one wired diagnostics interface must be present')
    nonce=secrets.token_bytes(4)
    with TransportLock(), hid.Device(path=devices[0]['path']) as device:
        device.write(b'\0F75E'+nonce+bytes(24));response=bytes(device.read(32,1000))
    if len(response)!=32 or response[:8]!=b'F75F'+nonce:raise RuntimeError('Lighting settings snapshot or nonce did not verify')
    result=dict(zip(['requested_effect','brightness','speed','reduced_motion'],response[8:12]))
    result.update(zip(['active_effect','pending_effect','buffer_hash','color_frames','active_buffer'],struct.unpack_from('<5I',response,12)))
    return result

def pwm_snapshot():
    devices=[d for d in hid.enumerate(0xfeed,0xf750) if d['usage_page']==0xff60]
    if len(devices)!=1:raise RuntimeError('Exactly one wired diagnostics interface must be present')
    nonce=secrets.token_bytes(4)
    with TransportLock(), hid.Device(path=devices[0]['path']) as device:
        device.write(b'\0F75X'+nonce+bytes(24));response=bytes(device.read(32,1000))
    if len(response)!=32 or response[:8]!=b'F75Y'+nonce:raise RuntimeError('PWM hardware snapshot or nonce did not verify')
    return dict(zip(['row','expected_duty','timer1_mr4','timer2_mr1','timer0_mr0','timer0_pwmctrl'],struct.unpack_from('<6I',response,8)))

def start_benchmark():
    devices = [d for d in hid.enumerate(0xfeed,0xf750) if d['usage_page']==0xff60]
    if len(devices)!=1: raise RuntimeError('Exactly one wired diagnostics interface must be present')
    nonce=secrets.token_bytes(4);request=b'F75A'+nonce+b'DRAWTEST'+bytes(16)
    with TransportLock(), hid.Device(path=devices[0]['path']) as device:
        device.write(b'\0'+request);response=bytes(device.read(32,1000))
    if response!=request: raise RuntimeError('Visual benchmark acknowledgement did not verify')
    return dict(visual_test_seconds=5,host_key_events=False,settings_changed=False)


def pwm_control_snapshot():
    devices=[d for d in hid.enumerate(0xfeed,0xf750) if d['usage_page']==0xff60]
    if len(devices)!=1:raise RuntimeError('Exactly one wired diagnostics interface must be present')
    nonce=secrets.token_bytes(4)
    with TransportLock(), hid.Device(path=devices[0]['path']) as device:
        device.write(b'\0F75C'+nonce+bytes(24));response=bytes(device.read(32,1000))
    if len(response)!=32 or response[:8]!=b'F75D'+nonce:raise RuntimeError('PWM control snapshot or nonce did not verify')
    return dict(zip(['timer0_mctrl','timer1_mctrl','timer2_mctrl','timer0_tc','timer1_tc','timer2_tc'],struct.unpack_from('<6I',response,8)))

def power_snapshot():
    devices=[d for d in hid.enumerate(0xfeed,0xf750) if d['usage_page']==0xff60]
    if len(devices)!=1:raise RuntimeError('Exactly one wired diagnostics interface must be present')
    nonce=secrets.token_bytes(4)
    with TransportLock(),hid.Device(path=devices[0]['path']) as device:
        device.write(b'\0F75d'+nonce+bytes(24));response=bytes(device.read(32,1000))
    if len(response)!=32 or response[:8]!=b'F75e'+nonce:raise RuntimeError('Power snapshot or nonce did not verify')
    values=struct.unpack_from('<6I',response,8)
    return dict(stage=['active','dim','off','sleep'][values[0]],rgb_percent=values[1],screen_budget=values[2],animation_fps=values[3],row_match_ticks=values[4],backlight_pin_high=bool(values[5]&1),pwm_banks_running=[bool(values[5]&(1<<bit)) for bit in (1,2,3)],scanner_running=bool(values[5]&16),idle_yields_mod65536=values[5]>>16)


def panel_bus_snapshot():
    devices=[d for d in hid.enumerate(0xfeed,0xf750) if d['usage_page']==0xff60]
    if len(devices)!=1:raise RuntimeError('Exactly one wired diagnostics interface must be present')
    nonce=secrets.token_bytes(4)
    with TransportLock(), hid.Device(path=devices[0]['path']) as device:
        device.write(b'\0F75I'+nonce+bytes(24));response=bytes(device.read(32,1000))
    if len(response)!=32 or response[:8]!=b'F75J'+nonce:raise RuntimeError('Panel bus counters or nonce did not verify')
    return dict(zip(['bytes','timeouts','overflows','max_sampled_byte_ticks','last_stat','last_ris'],struct.unpack_from('<6I',response,8)))


def diagnostic_action(action):
    commands={'rgb-off':b'RGB0','rgb-on':b'RGB1','rgb-scan-only':b'RGB2','panel-reset':b'LCD0'}
    command=commands[action]
    devices=[d for d in hid.enumerate(0xfeed,0xf750) if d['usage_page']==0xff60]
    if len(devices)!=1:raise RuntimeError('Exactly one wired diagnostics interface must be present')
    nonce=secrets.token_bytes(4)
    request=b'F75T'+nonce+b'F75DIAG!'+command+bytes(12)
    with TransportLock(), hid.Device(path=devices[0]['path']) as device:
        device.write(b'\0'+request);response=bytes(device.read(32,2000))
    if len(response)!=32 or response[:8]!=b'F75U'+nonce or response[16:20]!=command:
        raise RuntimeError('Diagnostic action acknowledgement did not verify')
    return dict(action=action,rgb_disabled=bool(response[8]),panel_ready=bool(response[9]),rgb_scan_only=bool(response[10]))


def radio_snapshot():
    devices=[d for d in hid.enumerate(0xfeed,0xf750) if d['usage_page']==0xff60]
    if len(devices)!=1:raise RuntimeError('Exactly one wired diagnostics interface must be present')
    nonce=secrets.token_bytes(4)
    with TransportLock(), hid.Device(path=devices[0]['path']) as device:
        device.write(b'\0F75O'+nonce+bytes(24));response=bytes(device.read(32,1000))
    if len(response)!=32 or response[:8]!=b'F75Z'+nonce:raise RuntimeError('Radio counters or nonce did not verify')
    flags,tx,rx,errors,event,status=struct.unpack_from('<6I',response,8)
    return dict(seen=bool(flags&1),connected_event=bool(flags&2),waiting_ack=bool(flags&4),report_queue_fault=bool(flags&8),
        selected=(flags>>8)&255,last_command=hex((flags>>16)&255),tx_packets=tx,rx_packets=rx,
        errors=errors,last_event=hex(event),uart_status=hex(status&255),uart_mux=hex((status>>8)&65535),
        rx_pin_high=bool(status&(1<<24)),tx_pin_high=bool(status&(1<<25)),
        uart_clock=bool(status&(1<<26)),uart_enabled=bool(status&(1<<27)))

def battery_snapshot():
    devices=[d for d in hid.enumerate(0xfeed,0xf750) if d['usage_page']==0xff60]
    if len(devices)!=1:raise RuntimeError('Exactly one wired diagnostics interface must be present')
    nonce=secrets.token_bytes(4)
    with TransportLock(), hid.Device(path=devices[0]['path']) as device:
        device.write(b'\0F75V'+nonce+bytes(24));response=bytes(device.read(32,1000))
    if len(response)!=32 or response[:8]!=b'F75W'+nonce:raise RuntimeError('Battery snapshot or nonce did not verify')
    valid,percent,mv,successes,failures,last_good=struct.unpack_from('<6I',response,8)
    return dict(valid=bool(valid),percent=percent if valid else None,millivolts=mv if valid else None,
                successful_samples=successes,failed_samples=failures,last_good_uptime_ms=last_good)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--battery',action='store_true',help='Read fixed gauge measurement and health counters; no gauge writes')
    parser.add_argument('--power',action='store_true',help='Read power budget, row clock and backlight pin; no state changes')
    parser.add_argument('--radio',action='store_true',help='Read fixed UART packet and connection counters; no key data')
    parser.add_argument('--pwm-control',action='store_true',help='Read fixed match-control and live PWM counter registers')
    parser.add_argument('--panel-bus',action='store_true',help='Read fixed SPI transfer and fault counters')
    parser.add_argument('--diagnostic',choices=['rgb-off','rgb-on','rgb-scan-only','panel-reset'],help='Explicitly disable/enable LEDs, run scanning without PWM pins, or reset the panel; RAM only')
    parser.add_argument('--pwm', action='store_true', help='Read intended duty and three fixed physical PWM match registers')
    parser.add_argument('--modes', action='store_true', help='Read four GPIO direction registers and fixed pad levels')
    parser.add_argument('--lighting', action='store_true', help='Read requested/applied lighting effect and active-buffer hash')
    parser.add_argument('--rgb', action='store_true', help='Read RGB driver counters, without changing lights')
    parser.add_argument('--boot', action='store_true', help='Explicitly request ROM entry; default is counters only')
    parser.add_argument('--gpio', action='store_true', help='Read fixed GPIO input/configuration registers')
    parser.add_argument('--aux', action='store_true', help='Read only matrix positions absent from the typing-key layout')
    parser.add_argument('--perf', action='store_true', help='Read display timings; ticks are 1/187500 second')
    parser.add_argument('--benchmark', action='store_true', help='Run a five-second display-only animation; sends no host keys')
    args = parser.parse_args()
    if args.power:
        print(json.dumps(power_snapshot(),indent=2));return
    if args.battery:
        print(json.dumps(battery_snapshot(),indent=2));return
    if args.radio:
        print(json.dumps(radio_snapshot(),indent=2));return
    if args.pwm_control:
        print(json.dumps(pwm_control_snapshot(),indent=2));return
    if args.panel_bus:
        print(json.dumps(panel_bus_snapshot(),indent=2));return
    if args.diagnostic:
        print(json.dumps(diagnostic_action(args.diagnostic),indent=2));return
    if args.benchmark:
        print(json.dumps(start_benchmark(),indent=2));return
    if args.perf:
        print(json.dumps(performance_snapshot(), indent=2)); return
    if args.aux:
        print(json.dumps(auxiliary_snapshot(), indent=2)); return
    if args.pwm:
        print(json.dumps(pwm_snapshot(),indent=2));return
    if args.modes:
        print(json.dumps(mode_snapshot(),indent=2));return
    if args.lighting:
        print(json.dumps(lighting_snapshot(),indent=2));return
    if args.rgb:
        print(json.dumps(rgb_snapshot(),indent=2));return
    if args.gpio:
        print(json.dumps(gpio_snapshot(), indent=2)); return
    if args.boot:
        print(json.dumps(exchange(True), indent=2)); return
    first = exchange(); time.sleep(.5); second = exchange()
    result = dict(first=first, second=second,
                  main_loop_advancing=second['uptime_ms'] > first['uptime_ms'] and second['matrix_scans'] > first['matrix_scans'],
                  display_transfers_advancing=second['complete_frames'] > first['complete_frames'])
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
