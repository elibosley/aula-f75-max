#!/usr/bin/env python3
"""Build an UNTESTED wired F75 Max candidate. Never opens a USB device."""
import argparse
import fcntl
import hashlib
import json
import os
import shlex
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
FAMILY_FLASH = 256 * 1024
STOCK_SHA = "a7d458754f3cc3aed7c8956f854148e081bc63f524da230a8ea8d3b3b3a4b5e9"
TARGET = "aula/f75max_test"
NAME = "aula_f75max_test_default"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare():
    source = ROOT / "firmware/targets/f75max"
    qmk = ROOT / "builddeps/qmk"
    if not (qmk / "quantum").is_dir():
        raise SystemExit("Missing pinned build dependencies; see firmware/targets/f75max/README.md")
    # The complete AHBCP word also contains DIV1P5. Upstream switches on the
    # whole word and divides by zero for valid values 8..15, before main().
    clock = ROOT / 'builddeps/chibios-contrib/os/common/ext/SONiX/SN32F2xx/system_SN32F290.c'
    before = '8651301c3732d54047f2a9cdd24e0225978af3aea26c5dbc5023547a59bb39c0'
    after = 'f57a00d37cd3c22cba22a6ae23db751e147581ee3addfe998a918dfa99ea618f'
    if digest(clock) == before:
        clock.write_bytes(clock.read_bytes().replace(b'switch (SN_SYS0->AHBCP)',
                                                    b'switch (SN_SYS0->AHBCP_b.AHBPRE)'))
    if digest(clock) != after:
        raise SystemExit('Clock source does not match the pinned one-line divider correction')
    spi_patch = json.loads((source / 'patches/spi-master-completion.json').read_text())
    spi = ROOT / spi_patch['source']
    if digest(spi) == spi_patch['before_sha256']:
        spi.write_bytes(spi.read_bytes().replace(bytes.fromhex(spi_patch['find_hex']),
                                               bytes.fromhex(spi_patch['replace_hex']), 1))
    if digest(spi) != spi_patch['after_sha256']:
        raise SystemExit('SPI source does not match the pinned master-completion correction')
    for patch in json.loads((source / 'patches/systick-timer4.json').read_text()):
        target = ROOT / patch['source']
        if digest(target) == patch['before_sha256']:
            target.write_bytes(bytes.fromhex(patch['after_hex']))
        if digest(target) != patch['after_sha256']:
            raise SystemExit('System timer source does not match pinned CT16B4 support')
    board = json.loads((ROOT / "firmware/targets/f75max/board-map.json").read_text())
    assert board["firmware_sha256"] == STOCK_SHA
    out = qmk / "keyboards" / TARGET
    out.mkdir(parents=True, exist_ok=True)
    for p in source.glob("*"):
        if p.suffix in {".c", ".h", ".mk", ".S"}:
            shutil.copy2(p, out / p.name)
    for p in (ROOT / "firmware").glob("*"):
        if p.name.startswith("f75_") and p.suffix in {".c", ".h"}:
            shutil.copy2(p, out / p.name)
    for n in ["font_data.h", "pet_assets.h", "font-license.txt"]:
        shutil.copy2(ROOT / "firmware" / n, out / n)

    def pin(p):
        port, bit = p[1:].split(".")
        return "ABCD"[int(port)] + bit

    coordinates = board["matrix"]["coordinates"]
    keys = [["KC_NO"] * 6 for _ in range(15)]
    layout, seen = [], set()
    for c in coordinates:
        k = c.get("vendor_key")
        if not k:
            continue
        usage = int(c["stock_usage"], 16)
        keys[c["scan_index"]][c["sense_bit"]] = "QK_USER_0" if k["name"] == "Fn" else hex(usage)
        if k["key_index"] in seen:
            continue
        seen.add(k["key_index"])
        layout.append(dict(label=k["name"], x=int(k["rect_left"])/40, y=int(k["rect_top"])/40,
                           matrix=[c["scan_index"], c["sense_bit"]]))
    assert len(seen) == 80
    info = {
        "keyboard_name": "F75 Max WIRED TEST",
        "manufacturer": "Experimental community firmware",
        "maintainer": "community",
        "processor": "SN32F299F",
        "bootloader": "sn32-dfu",
        "usb": {"vid": "0xFEED", "pid": "0xF750", "device_version": "0.0.1"},
        "matrix_pins": {"rows": [pin(p) for p in board["matrix"]["drive_pins"]],
                        "cols": [pin(p["pin"]) for p in board["matrix"]["sense_pins"]]},
        "diode_direction": "COL2ROW",
        "features": {"bootmagic": False, "mousekey": True, "extrakey": True,
                     "nkro": False, "encoder": True, "console": False, "command": False},
        "encoder": {"rotary": [{"pin_a": "A2", "pin_b": "A3", "resolution": 4}]},
        "layouts": {"LAYOUT": {"layout": layout}},
    }
    (out / "keyboard.json").write_text(json.dumps(info, indent=2) + "\n")
    km = out / "keymaps/default"
    km.mkdir(parents=True, exist_ok=True)
    (km / "keymap.c").write_text(
        '// Generated from the hash-checked supplier matrix.\n#include QMK_KEYBOARD_H\n'
        'const uint16_t PROGMEM keymaps[][MATRIX_ROWS][MATRIX_COLS] = {{\n' +
        ''.join('    {' + ', '.join(row) + '},\n' for row in keys) + '}};\n')
    commands = board["display"]["init_commands"]
    (out / "panel_init.h").write_text(
        '// Generated from the recovered stock initialization sequence.\n#pragma once\n'
        'typedef struct { uint8_t command, length, data[16]; } f75_panel_command;\n'
        'static const f75_panel_command f75_panel_commands[] = {\n' +
        ''.join('    {' + c['command'] + ', ' + str(len(c['data'])) + ', {' +
                ', '.join(str(v) for v in c['data']) + '}},\n' for c in commands) + '};\n')
    return qmk, out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--usb-only", action="store_true", help="Omit display initialization and its first-frame timer")
    parser.add_argument("--clean", action="store_true", help="Delete only this target's compiled objects before building")
    parser.add_argument("--output-dir", type=Path, default=ROOT / 'analysis/UNFLASHED')
    args = parser.parse_args()
    lock_path = ROOT / '.runtime/keyboard-build.lock'
    lock_path.parent.mkdir(exist_ok=True, mode=0o700)
    build_lock = os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(build_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise SystemExit('Another keyboard build is active; shared QMK objects were not changed')
    qmk, out = prepare()
    if args.usb_only:
        rules = out / 'rules.mk'
        rules.write_text(rules.read_text() + '\nOPT_DEFS += -DF75_USB_ONLY=1\n')
    rules = out / 'rules.mk'
    rules.write_text(rules.read_text() + f'\nOPT_DEFS += -ffile-prefix-map={ROOT}=/f75 -fdebug-prefix-map={ROOT}=/f75\n')
    if args.prepare_only:
        print(out)
        return
    toolchain = ROOT / "builddeps/arm-toolchain/bin"
    env = dict(os.environ)
    python_bin = Path(sys.executable).parent
    if not (python_bin / 'qmk').is_file():
        raise SystemExit('Install requirements-build.lock into the active Python environment first')
    env["PATH"] = str(toolchain) + os.pathsep + str(python_bin) + os.pathsep + env["PATH"]
    env["QMK_HOME"] = str(qmk)
    # QMK's supported placeholder-version mode removes wall-clock and Git
    # metadata from generated version.h. GCC also receives a fixed epoch.
    env.update(SKIP_VERSION='yes', SOURCE_DATE_EPOCH='0', TZ='UTC', LC_ALL='C')
    if args.clean:
        shutil.rmtree(qmk / '.build' / ('obj_' + NAME), ignore_errors=True)
        for suffix in ['.bin', '.elf', '.map', '.hex']:
            (qmk / '.build' / (NAME + suffix)).unlink(missing_ok=True)
    cmd = [str(python_bin / 'qmk'), "compile", "-kb", TARGET, "-km", "default"]
    log = ROOT / "analysis/keyboard-build.log"
    with log.open("w") as f:
        result = subprocess.run(cmd, cwd=qmk, env=env, stdout=f, stderr=subprocess.STDOUT, timeout=240)
    if result.returncode:
        print("\n".join(log.read_text().splitlines()[-30:]))
        raise SystemExit(result.returncode)
    build = qmk / ".build"
    binary = build / (NAME + ".bin")
    elf = build / (NAME + ".elf")
    data = binary.read_bytes()
    sp, reset = struct.unpack_from("<II", data)
    assert 0x20000000 < sp <= 0x20008000 and sp % 8 == 0
    assert reset & 1 and (reset & ~1) < len(data)
    assert len(data) == FAMILY_FLASH
    assert data[0x3f000:0x3f800] == b'\xff'*2048, 'Application overlaps reserved settings pages'
    assert data[0x38000:0x3a000] == b'\xff'*8192, 'Application overlaps customization records'
    assert data[-4:] == struct.pack("<I", 0xAAAA5555)
    dest = args.output_dir.resolve()
    dest.mkdir(parents=True, exist_ok=True)
    artifacts = {}
    for suffix in [".bin", ".elf", ".map"]:
        p = build / (NAME + suffix)
        d = dest / ("f75max-wired-test" + suffix)
        shutil.copy2(p, d)
        artifacts[d.name] = {"sha256": digest(d), "bytes": d.stat().st_size}
    size = subprocess.check_output([str(toolchain / "arm-none-eabi-size"), str(elf)], text=True)
    symbols = {}
    for line in subprocess.check_output([str(toolchain / "arm-none-eabi-nm"), '-n', str(elf)], text=True).splitlines():
        fields = line.split()
        if len(fields) == 3:
            symbols[fields[2]] = int(fields[0], 16)
    memory = {
        "initialized_data": symbols['__data_end__'] - symbols['__data_base__'],
        "zero_initialized_globals": symbols['__bss_end__'] - symbols['__bss_base__'],
        "main_stack_reserved": symbols['__main_stack_size__'],
        "process_stack_reserved": symbols['__process_stack_size__'],
        "ram_prefix_including_stacks_and_alignment": symbols['__ram0_free__'] - 0x20000000,
        "available_heap_reservation": symbols['__heap_end__'] - symbols['__heap_base__'],
        "runtime_stack_high_water": "not_measured",
    }
    assert memory['ram_prefix_including_stacks_and_alignment'] < 0x8000
    assert memory['available_heap_reservation'] >= 4096
    assert (reset & ~1) == symbols['Reset_Handler'] == symbols['f75_recovery_begin']
    recovery = dict(start=symbols['f75_recovery_begin'], end=symbols['f75_recovery_end'],
                    rom_entry=symbols['f75_enter_rom'], before_c_runtime=True)
    recovery['sha256'] = hashlib.sha256(data[recovery['start']:recovery['end']]).hexdigest()
    recovery['hardfault_entry'] = symbols['HardFault_Handler']
    recovery['wheel_button'] = dict(source='matrix', row=symbols['f75_wheel_matrix_row'],
                                    column=symbols['f75_wheel_matrix_col'], drive='C9', sense='B14', active_level='high')
    assert recovery['start'] < recovery['hardfault_entry'] < recovery['end']
    assert struct.unpack_from('<I', data, 12)[0] == symbols['HardFault_Handler'] | 1
    # GCC dependency files bind this image to every included local source and
    # header, including generated headers and patched upstream drivers.
    inputs = set()
    # Assembly and make rules do not always emit GCC dependency files.
    inputs.update(p.resolve() for p in out.rglob('*') if p.is_file())
    for dependency in (build / ('obj_' + NAME)).rglob('*.d'):
        rule = dependency.read_text().replace('\\\n', ' ').split('\n')[0]
        for name in shlex.split(rule.split(':', 1)[1]):
            path = (qmk / name).resolve()
            if path.is_file():
                inputs.add(path)
    input_hashes = {str(p.relative_to(ROOT)): digest(p) for p in sorted(inputs) if p.is_relative_to(ROOT)}
    assert len(input_hashes) > 100, 'Build input dependency capture is incomplete'
    shutil.copy2(log, dest / 'build.log')
    (dest / 'build-inputs.json').write_text(json.dumps(input_hashes, indent=2) + '\n')
    receipt = {
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "status": "linked_candidate_not_hardware_tested",
        "flash_authorized_by_user": True,
        "hardware_writes": False,
        "stock_source_sha256": STOCK_SHA,
        "target": TARGET,
        "profile": "usb_only" if args.usb_only else "full_ui",
        "usb_identity": "feed:f750 F75 Max WIRED TEST",
        "family_memory_assumption": "SN32 family 0x32 chip 0x05; 256 KiB flash / 32 KiB SRAM target",
        "reproducibility": {"source_date_epoch": 0, "qmk_version_mode": "skip-all", "clean": args.clean},
        "build_inputs_sha256": digest(dest / 'build-inputs.json'),
        "initial_sp": hex(sp), "reset_handler": hex(reset),
        "reset_recovery": recovery,
        "artifacts": artifacts, "size_output": size, "ram_bytes": memory,
        "source_sha256": {str(p.relative_to(ROOT)): digest(p)
                          for p in sorted(out.rglob('*')) if p.is_file()},
        "dependencies": json.loads((ROOT / "builddeps/sources.json").read_text()),
        "local_dependency_patches": [{
            "patch": "firmware/targets/f75max/patches/clock-divider.patch",
            "patch_sha256": digest(ROOT / 'firmware/targets/f75max/patches/clock-divider.patch'),
            "source_sha256": digest(ROOT / 'builddeps/chibios-contrib/os/common/ext/SONiX/SN32F2xx/system_SN32F290.c'),
        }, {
            "patch": "firmware/targets/f75max/patches/spi-master-completion.patch",
            "patch_sha256": digest(ROOT / 'firmware/targets/f75max/patches/spi-master-completion.patch'),
            "source_sha256": digest(ROOT / 'builddeps/chibios-contrib/os/hal/ports/SN32/LLD/SN32F2xx/SPI/hal_spi_v2_lld.c'),
        }],
        "toolchain": json.loads((ROOT / "builddeps/toolchain.json").read_text()),
        "system_timer_patch_sha256": digest(ROOT / 'firmware/targets/f75max/patches/systick-timer4.json'),
        "missing": ["corrected wheel-entry hardware qualification", "hardware validation",
                    "wireless", "RGB physical color qualification", "battery measurements", "persistent settings", "RTC synchronization"],
    }
    (dest / "f75max-wired-test.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(size.strip())
    print("UNFLASHED candidate: " + str(dest / "f75max-wired-test.bin"))


if __name__ == "__main__":
    main()
