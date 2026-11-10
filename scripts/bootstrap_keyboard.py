#!/usr/bin/env python3
"""Fetch hash-pinned build tools and sources. Does not access keyboard USB."""
import hashlib
import json
from pathlib import Path
import tarfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
DEPS = ROOT / 'builddeps'
MANIFEST = ROOT / 'firmware/targets/f75max/dependencies.json'


def acquire(name, url, expected):
    archive = DEPS / (name + '.tar.gz')
    if not archive.exists():
        temporary = archive.with_suffix('.part')
        with urllib.request.urlopen(url, timeout=45) as response, temporary.open('wb') as output:
            while chunk := response.read(1024 * 1024):
                output.write(chunk)
        temporary.replace(archive)
    with archive.open('rb') as stream:
        actual = hashlib.file_digest(stream, 'sha256').hexdigest()
    if actual != expected:
        raise RuntimeError(f'Archive checksum mismatch: {name}')
    dest = DEPS / name
    if not dest.exists():
        with tarfile.open(archive) as package:
            top = package.getnames()[0].split('/')[0]
            package.extractall(DEPS, filter='data')
        (DEPS / top).rename(dest)
    print(f'{name}: archive verified')


def main():
    manifest = json.loads(MANIFEST.read_text())
    DEPS.mkdir(exist_ok=True)
    for item in manifest['sources']:
        url = f'https://codeload.github.com/{item["repo"]}/tar.gz/{item["revision"]}'
        acquire(item['name'], url, item['archive_sha256'])
    toolchain = manifest['toolchain']
    # Reuse the initially downloaded release archive without downloading it again.
    original = DEPS / toolchain['url'].rsplit('/', 1)[1]
    cached = DEPS / 'arm-toolchain.tar.gz'
    if original.exists() and not cached.exists():
        cached.hardlink_to(original)
    acquire('arm-toolchain', toolchain['url'], toolchain['sha256'])
    for name in ['chibios', 'chibios-contrib', 'printf', 'lufa']:
        path = DEPS / 'qmk/lib' / name
        desired = DEPS / name
        if path.is_symlink():
            if path.resolve() != desired:
                raise RuntimeError(f'Unexpected dependency link: {path}')
        else:
            path.rmdir()  # refuse to replace a nonempty checkout
            path.symlink_to(desired, target_is_directory=True)
    (DEPS / 'sources.json').write_text(json.dumps(manifest['sources'], indent=2) + '\n')
    (DEPS / 'toolchain.json').write_text(json.dumps(toolchain, indent=2) + '\n')


if __name__ == '__main__':
    main()
