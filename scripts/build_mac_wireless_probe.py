#!/usr/bin/env python3
"""Build an optional local Mac HID probe. Never requests access or opens HID."""
import hashlib, json, os, pathlib, plistlib, subprocess

ROOT = pathlib.Path(__file__).resolve().parents[1]
os.umask(0o077)
app = ROOT / '.runtime/F75 Wireless Probe.app'
contents = app / 'Contents'
binary = contents / 'MacOS/F75WirelessProbe'
binary.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
info = {'CFBundleIdentifier': 'com.elibosley.f75-wireless-probe',
        'CFBundleName': 'F75 Wireless Probe', 'CFBundleDisplayName': 'F75 Wireless Probe',
        'CFBundleExecutable': binary.name, 'CFBundlePackageType': 'APPL',
        'CFBundleVersion': '1', 'CFBundleShortVersionString': '0.1',
        'LSUIElement': True, 'F75ProjectRoot': str(ROOT),
        'NSInputMonitoringUsageDescription': 'Exchange configuration data with this enrolled keyboard. Probe checks count key events without recording key codes or text.'}
(contents / 'Info.plist').write_bytes(plistlib.dumps(info))
source = ROOT / 'scripts/mac_wireless_probe.m'
subprocess.run(['xcrun', 'clang', '-fobjc-arc', '-Wall', '-Wextra', '-Werror',
                '-Wno-deprecated-declarations', '-framework', 'Foundation', '-framework', 'IOKit', '-framework', 'CoreGraphics', '-framework', 'AppKit',
                str(source), '-o', str(binary)], check=True)
binary.chmod(0o700)
subprocess.run(['codesign', '--force', '--sign', '-', '--identifier', info['CFBundleIdentifier'], str(app)], check=True)
subprocess.run(['codesign', '--verify', '--strict', str(app)], check=True)
receipt = {'app': str(app.relative_to(ROOT)), 'bundle_id': info['CFBundleIdentifier'],
           'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
           'binary_sha256': hashlib.sha256(binary.read_bytes()).hexdigest(),
           'hardware_accessed': False, 'permission_requested': False,
           'scope': 'Check access by default. Explicit modes can request access, open an enrolled Bluetooth device, test Num Lock output, or send temporary display text.'}
(ROOT / '.runtime/mac-wireless-probe-build.json').write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(receipt))
