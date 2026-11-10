#!/usr/bin/env python3
"""Build an UNFLASHED wheel customization prototype for one exact firmware."""
import argparse
import hashlib
import json
from pathlib import Path
import struct

import pefile

ROOT = Path(__file__).resolve().parents[1]
UPDATER_SHA = "a6ac9d2e4dc1e14c6f3002f40bc889b553018dd205e857bb18283dab3338d6ac"
APPLICATION_SHA = "a7d458754f3cc3aed7c8956f854148e081bc63f524da230a8ea8d3b3b3a4b5e9"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def word_sum(data):
    return sum(x[0] for x in struct.iter_unpack("<H", data)) & 0xFFFF


def rcdata(pe, resource_id):
    for kind in pe.DIRECTORY_ENTRY_RESOURCE.entries:
        if kind.id != 10:
            continue
        for item in kind.directory.entries:
            if item.id == resource_id:
                langs = item.directory.entries
                if len(langs) != 1:
                    raise ValueError("Ambiguous firmware resource languages")
                resource = langs[0].data.struct
                return pe.get_offset_from_rva(resource.OffsetToData), resource.Size
    raise ValueError(f"Missing resource {resource_id}")


def patch_application(data, *, reverse=False, debounce_samples=5, positive_usage=None, negative_usage=None):
    if sha(data) != APPLICATION_SHA:
        raise ValueError("Unsupported application SHA-256; refusing a different firmware revision")
    if isinstance(debounce_samples, bool) or not 1 <= debounce_samples <= 255:
        raise ValueError("Debounce samples must be in 1..255")
    positive_usage = 0xE9 if positive_usage is None else positive_usage
    negative_usage = 0xEA if negative_usage is None else negative_usage
    for value in (positive_usage, negative_usage):
        if isinstance(value, bool) or not 0 <= value <= 255:
            raise ValueError("This prototype supports only 8-bit Consumer-page usages")
    menu_positive, menu_negative = 8, 9
    if reverse:
        positive_usage, negative_usage = negative_usage, positive_usage
        menu_positive, menu_negative = menu_negative, menu_positive
    expected = {0x2212: 5, 0x2260: 8, 0x2296: 0xE9, 0x22C6: 9, 0x2300: 0xEA}
    replacements = {0x2212: debounce_samples, 0x2260: menu_positive, 0x2296: positive_usage,
                    0x22C6: menu_negative, 0x2300: negative_usage}
    out = bytearray(data)
    for offset, original in expected.items():
        if data[offset] != original or data[offset + 1] not in (0x20, 0x21):
            raise ValueError(f"Unexpected instruction at {offset:#x}")
        out[offset] = replacements[offset]
    return bytes(out)


def patch_updater(data, **settings):
    if sha(data) != UPDATER_SHA:
        raise ValueError("Unsupported updater SHA-256; refusing a different vendor package")
    pe = pefile.PE(data=data)
    offset, length = rcdata(pe, 4000)
    checksum_offset, checksum_length = rcdata(pe, 4014)
    if length != 262144 or checksum_length != 8:
        raise ValueError("Unexpected vendor resource sizes")
    original = data[offset:offset + length]
    if data[checksum_offset:checksum_offset + 8].decode("utf-16le") != f"{word_sum(original):04X}":
        raise ValueError("Original embedded firmware checksum does not match")
    payload = patch_application(original, **settings)
    result = bytearray(data)
    result[offset:offset + length] = payload
    result[checksum_offset:checksum_offset + 8] = f"{word_sum(payload):04X}".encode("utf-16le")
    repacked = pefile.PE(data=bytes(result))
    repacked.OPTIONAL_HEADER.CheckSum = repacked.generate_checksum()
    result = repacked.write()
    if not pefile.PE(data=result).verify_checksum():
        raise ValueError("Repacked PE checksum is invalid")
    return result, payload


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--updater", type=Path, default=ROOT / "raw/supplier-f75max-firmware.exe")
    parser.add_argument("--output", type=Path, default=ROOT / "analysis/UNFLASHED/wheel-reversed.exe")
    parser.add_argument("--reverse", action="store_true")
    parser.add_argument("--debounce-samples", type=int, default=5)
    parser.add_argument("--positive-usage", type=lambda s: int(s, 0))
    parser.add_argument("--negative-usage", type=lambda s: int(s, 0))
    args = parser.parse_args()
    settings = {k: getattr(args, k) for k in ("reverse", "debounce_samples", "positive_usage", "negative_usage")}
    result, payload = patch_updater(args.updater.read_bytes(), **settings)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists() or args.output.with_suffix(".bin").exists():
        raise FileExistsError("Refusing to overwrite a prior prototype")
    with args.output.open("xb") as out:
        out.write(result)
    args.output.with_suffix(".bin").write_bytes(payload)
    original = (ROOT / "analysis/firmware/supplier-f75max-firmware/application.bin").read_bytes()
    metadata = {"status": "UNFLASHED; emulator validation is not hardware validation",
                "source_sha256": UPDATER_SHA, "updater_sha256": sha(result),
                "application_sha256": sha(payload), "application_word_sum16": f"{word_sum(payload):04X}",
                "settings": settings, "application_changes": [
                    {"offset": hex(i), "before": f"{a:02x}", "after": f"{b:02x}"}
                    for i, (a, b) in enumerate(zip(original, payload)) if a != b],
                "firmware_version_policy": "unchanged; this prototype does not establish updater admission or recovery"}
    args.output.with_suffix(".json").write_text(json.dumps(metadata, indent=2) + "\n")
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
