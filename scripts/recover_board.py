#!/usr/bin/env python3
"""Recover a board model from firmware instructions and vendor layout data."""
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

from emulate import APPLICATION, Firmware, GPIO, ROOT, display_init, matrix_outputs


def pin_name(address, mask):
    if mask == 0 or mask & (mask - 1):
        raise ValueError("Expected one GPIO bit")
    for port, base in enumerate(GPIO):
        if address in (base, base + 0x24, base + 0x28):
            return f"P{port}.{mask.bit_length() - 1}"
    raise ValueError(f"Unknown GPIO register {address:#x}")


def recover():
    data = APPLICATION.read_bytes()
    xml = ET.parse(ROOT / "analysis/windows-driver/app/layouts/rgb-keyboard.xml")
    keys = {int(k.attrib["key_index"]): dict(k.attrib) for k in xml.findall(".//key")}
    outputs = matrix_outputs()[:15]  # The scanner wraps at 15 at 0x6160 and 0x620e.
    drive = [pin_name(item["writes"][0]["address"], item["writes"][0]["value"]) for item in outputs]
    sense = []
    # Execute the actual scanner with one input pin high at a time.
    for port, base in enumerate(GPIO):
        for bit in range(20):
            fw = Firmware(stubs=[0x3ADA, 0x3AC2, 0x39F6, 0x7DCA])
            fw.word(base, 1 << bit)
            result = fw.run(0x3AFC)
            if result:
                sense.append({"pin": f"P{port}.{bit}", "sense_bit": result.bit_length() - 1,
                              "value": result})
    sense.sort(key=lambda r: r["sense_bit"])
    coordinates = []
    for scan in range(15):
        for sense_bit in range(6):
            index = scan * 8 + sense_bit
            vendor_id = data[0x13BE0 + index]
            usage = data[0x13C88 + index]
            vendor = keys.get(vendor_id)
            coordinates.append({"scan_index": scan, "sense_bit": sense_bit,
                                "drive_pin": drive[scan], "sense_pin": sense[sense_bit]["pin"],
                                "vendor_key_index": vendor_id, "stock_usage": f"0x{usage:02x}",
                                "vendor_key": vendor})
    fw = Firmware()
    fw.run(0xA38)
    mux = fw.word(0x40042010)
    display = display_init()
    command_stream = []
    for call in display["calls"]:
        if call["address"] == 0x68EC:
            command_stream.append({"command": f"0x{call['args'][0]:02x}", "data": []})
        elif call["address"] == 0x68E4:
            command_stream[-1]["data"].append(call["args"][0])
    missing = sorted(set(keys) - {c["vendor_key_index"] for c in coordinates})
    return {
        "scope": "Derived from the downloaded F75 Max application image. Not verified on the connected hardware.",
        "firmware_sha256": hashlib.sha256(data).hexdigest(),
        "controller_family": {"value": "SN32F29x / ARM Cortex-M0",
                              "evidence": ["Cortex-M vector table", "SN32F290 peripheral addresses", "updater configuration and embedded SN32F290.hex"],
                              "exact_package": "not established"},
        "matrix": {"scan_function": "0x3afc", "drive_function": "0x39f6", "active_level": "high",
                   "drive_count": 15, "sense_count": 6, "drive_pins": drive, "sense_pins": sense,
                   "vendor_layout_keys": len(keys), "unmatched_vendor_keys": missing,
                   "translation_table": "0x13be0", "default_usage_table": "0x13c88", "coordinates": coordinates},
        "encoder": {"function": "0x21f0", "a": "P0.2", "b": "P0.3", "debounce_samples": 5,
                    "button_function": "0x2184", "button": "P1.17", "button_active_level": "low",
                    "button_debounce_samples": 50, "mode_flag": "0x2000004e",
                    "media_usages": ["0xe9", "0xea"], "menu_events": [8, 9], "event_queue_function": "0x107a8"},
        "spi_pin_assignment": {"register": "0x40042010", "value": f"0x{mux:04x}",
                               "spi0": {"select": "P1.8", "clock": "P3.0", "mosi": "P3.2", "miso": "P3.1"},
                               "spi1": {"select": "P0.13", "clock": "P0.12", "mosi": "P1.11", "miso": "P1.10"}},
        "display": {"dimensions": [128, 128], "pixel_format": "RGB565", "bus": "SPI0",
                    "select": "P1.8", "data_command": "P3.14", "reset": "P0.17", "backlight": "P0.16",
                    "init_function": "0x69f6", "command_function": "0x68ec", "byte_function": "0x8e24",
                    "offsets": [display["offset_x"], display["offset_y"]], "init_commands": command_stream,
                    "controller": "ST7735-style command set; exact panel controller not established",
                    "image_transfer": "0x6ce0 reads pixels from external SPI flash through SPI1; this is not a RAM framebuffer function"},
        "replacement_firmware": {"candidate": "SonixQMK sn32_develop",
                                 "reference_commit": "c9f3803ff1cb910a713c6202cab357268cf98fa6",
                                 "family_example": "keyboards/handwired/onekey/sn32f290/keyboard.json",
                                 "board_port_status": "not built or hardware tested",
                                 "remaining": ["exact application/bootloader update contract and recovery", "wireless and RGB ownership", "firmware-to-device compatibility"]},
    }


def main():
    board = recover()
    target = ROOT / "analysis/board-map.json"
    target.write_text(json.dumps(board, indent=2) + "\n")
    print(json.dumps({"output": str(target), "drive_pins": board["matrix"]["drive_pins"],
                      "sense_pins": board["matrix"]["sense_pins"],
                      "matched_vendor_keys": board["matrix"]["vendor_layout_keys"] - len(board["matrix"]["unmatched_vendor_keys"]),
                      "unmatched_vendor_keys": board["matrix"]["unmatched_vendor_keys"],
                      "spi_pin_assignment": board["spi_pin_assignment"]}, indent=2))


if __name__ == "__main__":
    main()
