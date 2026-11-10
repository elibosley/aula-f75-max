#!/usr/bin/env python3
"""Download research inputs as data. Never execute vendor software."""
import concurrent.futures
import datetime
import hashlib
import json
from pathlib import Path
import re
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; KeyboardFirmwareResearch/1.0)"}


def fetch(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=35) as r:
        data = r.read(40 * 1024 * 1024 + 1)
        if len(data) > 40 * 1024 * 1024:
            raise ValueError("Research download exceeds 40 MiB")
        return data, r.headers.get("Content-Disposition"), r.geturl()


def download(item):
    name, url = item
    dest = ROOT / "raw" / name
    try:
        if dest.exists():
            return {"name": name, "status": "existing", "sha256": hashlib.sha256(dest.read_bytes()).hexdigest()}
        data, disposition, final_url = fetch(url)
        dest.write_bytes(data)
        return {"name": name, "url": url, "final_url": final_url, "content_disposition": disposition,
                "size": len(data), "sha256": hashlib.sha256(data).hexdigest(),
                "observed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(), "status": "downloaded"}
    except Exception as exc:
        return {"name": name, "url": url, "status": "error", "error": str(exc)}


def main():
    html, _, _ = fetch("https://www.aulastar.com/keyboard")
    match = re.search(rb'href=["\x27]([^"\x27]*aid=549[^"\x27]*)', html)
    if not match:
        raise ValueError("No current F75 Max driver link")
    items = [
        ("official-driver-1.0.0.5.exe", "https://www.aulastar.com" + match[1].decode().replace("&amp;", "&")),
        ("supplier-f75max-firmware.exe", "https://mykeeb.com/wp-content/uploads/2026/09/f75max-firmware.exe"),
        ("supplier-f75max-v1.08.exe", "https://mykeeb.com/wp-content/uploads/2026/10/aula-f75max-si-2806-3mode-display-firmware-v1.08-20240919.exe"),
        ("sn32f290-datasheet.pdf", "https://www.sonix.com.tw/webapi/fl219871/SN32F297_V1.8_EN.pdf"),
    ]
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        records = list(pool.map(download, items))
    manifest = ROOT / "analysis" / "downloads.json"
    previous = json.loads(manifest.read_text()) if manifest.exists() else []
    by_name = {r["name"]: r for r in previous}
    for r in records:
        if r["status"] != "existing":
            by_name[r["name"]] = r
        elif r["name"] not in by_name:
            by_name[r["name"]] = r
    manifest.write_text(json.dumps(list(by_name.values()), indent=2) + "\n")
    print(json.dumps(records, indent=2))


if __name__ == "__main__":
    main()
