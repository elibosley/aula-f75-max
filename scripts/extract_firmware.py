#!/usr/bin/env python3
"""Extract PE resources and characterize firmware without hardware access."""
import hashlib
import io
import json
from pathlib import Path
import re
import struct
import zipfile

import pefile

ROOT = Path(__file__).resolve().parents[1]


def checksum(data):
    if len(data) % 2:
        raise ValueError("Word checksum requires even length")
    return sum(struct.unpack("<" + "H" * (len(data) // 2), data)) & 0xFFFF


def inspect(path):
    pe = pefile.PE(str(path))
    dest = ROOT / "analysis" / "firmware" / path.stem
    dest.mkdir(parents=True, exist_ok=True)
    resources = []
    for kind in pe.DIRECTORY_ENTRY_RESOURCE.entries:
        if kind.id != pefile.RESOURCE_TYPE["RT_RCDATA"]:
            continue
        for resource in kind.directory.entries:
            name = str(resource.name) if resource.name else str(resource.id)
            for lang in resource.directory.entries:
                entry = lang.data.struct
                data = pe.get_data(entry.OffsetToData, entry.Size)
                safe_name = re.sub(r"[^a-zA-Z0-9_-]", "_", name)
                target = dest / ("rcdata-" + safe_name + ".bin")
                target.write_bytes(data)
                record = {"id": name, "language": lang.id, "size": len(data),
                          "sha256": hashlib.sha256(data).hexdigest(),
                          "file_offset": hex(pe.get_offset_from_rva(entry.OffsetToData)),
                          "path": str(target.relative_to(ROOT))}
                if name == "4000":
                    vectors = struct.unpack_from("<16I", data)
                    record.update({"initial_sp": hex(vectors[0]), "reset_handler": hex(vectors[1]),
                                   "vectors": [hex(v) for v in vectors],
                                   "word_sum16": f"{checksum(data):04X}",
                                   "trailer": data[-4:].hex(),
                                   "f75_strings": [hex(m.start()) for m in re.finditer(b"A\x00U\x00L\x00A\x00|AULA", data)]})
                    (dest / "application.bin").write_bytes(data)
                if zipfile.is_zipfile(io.BytesIO(data)):
                    with zipfile.ZipFile(io.BytesIO(data)) as archive:
                        record["zip_entries"] = archive.namelist()
                        for item in archive.infolist():
                            # Vendor archives contain Windows separators. Reject traversal.
                            parts = Path(item.filename.replace("\\", "/")).parts
                            if item.is_dir():
                                continue
                            if any(p in ("..", "/") for p in parts) or item.file_size > 20 * 1024 * 1024:
                                raise ValueError("Unsafe embedded archive entry")
                            out = dest / "embedded" / Path(*parts)
                            out.parent.mkdir(parents=True, exist_ok=True)
                            out.write_bytes(archive.read(item))
                if name == "4014":
                    record["text"] = data.decode("utf-16le", errors="replace").rstrip("\0")
                resources.append(record)
    report = {"source": str(path.relative_to(ROOT)), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
              "pe_checksum_valid": pe.verify_checksum(), "resources": resources}
    (dest / "resources.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def main():
    paths = list((ROOT / "raw").glob("*firmware*.exe"))
    paths += list((ROOT / "raw").glob("*v1.08.exe"))
    paths += list((ROOT / "reference" / "AULA-F75-Max-Firmware-Fix---Space-Fn-Ctrl").glob("*.exe"))
    for path in sorted(set(paths)):
        report = inspect(path)
        print(json.dumps({"source": report["source"], "pe_checksum_valid": report["pe_checksum_valid"],
                          "resources": [{k: v for k, v in r.items() if k not in ("zip_entries",)} for r in report["resources"]]}))


if __name__ == "__main__":
    main()
