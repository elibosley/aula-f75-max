#!/usr/bin/env python3
"""Inventory the keyboard without rebooting, erasing, or changing security."""
import argparse
import datetime
import json
from pathlib import Path
import plistlib
import subprocess

import hid
import usb.backend.libusb1
import usb.core

ROOT = Path(__file__).resolve().parents[1]


def inventory(boot_info=False):
    backend = usb.backend.libusb1.get_backend(find_library=lambda _: "/opt/homebrew/lib/libusb-1.0.dylib")
    if backend is None:
        raise RuntimeError("libusb backend unavailable; device absence cannot be established")
    devices = list(usb.core.find(find_all=True, backend=backend))
    sonix = [dict(vid=f"{d.idVendor:04x}", pid=f"{d.idProduct:04x}",
                  revision=f"{d.bcdDevice:04x}", bus=d.bus, address=d.address)
             for d in devices if d.idVendor == 0x0c45 or (d.idVendor, d.idProduct) == (0xfeed, 0xf750)]
    interfaces = []
    for d in hid.enumerate(0x0c45, 0):
        # Do not retain USB serial numbers or paths of unrelated devices.
        interfaces.append({k: getattr(v, 'value', v) for k, v in d.items()
                           if k not in {"path", "serial_number"}})
    registry = plistlib.loads(subprocess.check_output(["ioreg", "-a", "-p", "IOUSB"]))
    entries = []

    def walk(node):
        if isinstance(node, dict):
            if "AULA" in node.get("IORegistryEntryName", ""):
                fields = ["IORegistryEntryName", "IOServiceState", "idVendor", "idProduct", "bcdDevice", "locationID"]
                entries.append({k: node[k] for k in fields if k in node})
            for child in node.get("IORegistryEntryChildren", []):
                walk(child)
        elif isinstance(node, list):
            for child in node:
                walk(child)

    walk(registry)
    result = dict(observed_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                  usb_devices=sonix, hid_interfaces=interfaces, registry_entries=entries,
                  bootloader_entry_requested=False, erase_requested=False,
                  security_change_requested=False, programming_requested=False,
                  device_reports_sent=False,
                  status="usb_present" if sonix else "keyboard_not_available_on_usb")
    if boot_info:
        boot = [d for d in sonix if (d["vid"], d["pid"]) == ("0c45", "7140")]
        if len(boot) != 1:
            raise RuntimeError("Exactly one 0c45:7140 bootloader must already be present for --boot-info")
        flasher = ROOT / "builddeps/flasher/sonixflasher"
        # Audited --info branch sends version/checksum queries only. No -r or -f.
        command = [str(flasher), "--vid-pid", "0c45/7140", "--info"]
        query = subprocess.run(command, capture_output=True, text=True, timeout=35)
        result.update(device_reports_sent=True, boot_info_exit=query.returncode,
                      boot_info_stdout=query.stdout, boot_info_stderr=query.stderr)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--boot-info", action="store_true", help="Query an already-present 7140 bootloader; never request entry")
    args = parser.parse_args()
    result = inventory(args.boot_info)
    path = ROOT / "analysis/keyboard-live-probe.json"
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(result, indent=2) + "\n")
    temporary.replace(path)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
