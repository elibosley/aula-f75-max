"""Native bundle version must match the release metadata before signing."""
import plistlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import build_desktop


class DesktopVersionTest(unittest.TestCase):
    def test_stamp_preserves_bundle_identity_and_sets_both_versions(self):
        with tempfile.TemporaryDirectory() as temporary:
            app = Path(temporary)/'Studio.app'
            path = app/'Contents/Info.plist'
            path.parent.mkdir(parents=True)
            path.write_bytes(plistlib.dumps(dict(CFBundleIdentifier='com.f75studio.desktop',
                                                CFBundleShortVersionString='0.0.0')))
            build_desktop.stamp_macos_version(app, build_desktop.bundle_version())
            metadata = plistlib.loads(path.read_bytes())
            self.assertEqual(metadata['CFBundleShortVersionString'], build_desktop.bundle_version())
            self.assertEqual(metadata['CFBundleVersion'], build_desktop.bundle_version())
            self.assertEqual(metadata['CFBundleIdentifier'], 'com.f75studio.desktop')

    def test_version_is_numeric_and_invalid_metadata_fails_before_build(self):
        with patch('build_desktop.json.loads', return_value={'version':'1.2.3;bad'}):
            with self.assertRaises(ValueError):
                build_desktop.bundle_version()
