"""Release assembly rejects incomplete, changed or mismatched build outputs."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import release_artifacts as release

COMMIT='a'*40

class ReleaseArtifactsTest(unittest.TestCase):
    def fixtures(self,root):
        for name in release.ASSETS:
            path=root/name
            if name.startswith('F75-Studio-firmware-'):
                target=name.removeprefix('F75-Studio-firmware-').removesuffix('.zip')
                profiles={}
                with zipfile.ZipFile(path,'w') as archive:
                    for profile in (['full_ui'] if target=='s75pro' else ['full_ui','usb_only']):
                        binary=(target+profile).encode()
                        archive.writestr(f'{profile}/{target}-wired-test.bin',binary)
                        archive.writestr(f'{profile}/{target}-wired-test.elf',binary)
                        profiles[profile]=dict(status='passed',identical_clean_builds=2,sha256={ext:hashlib.sha256(binary).hexdigest() for ext in ('bin','elf')})
                    archive.writestr('SOURCE.json',json.dumps(dict(commit=COMMIT,target=target)))
                    archive.writestr('verification.json',json.dumps(dict(status='passed',source_commit=COMMIT,target=target,profiles=profiles)))
                    archive.writestr('corresponding-source.tar.gz',b'fixture source')
            else:path.write_bytes(name.encode())
            (root/(name+'.json')).write_text(json.dumps(dict(file=name,sha256=release.sha(path),bytes=path.stat().st_size,source_commit=COMMIT,version='0.2.0')))
    def assemble(self,root):
        with patch.object(release,'head',return_value=COMMIT),patch.object(release,'version',return_value='0.2.0'):
            return release.assemble(root,COMMIT,'v0.2.0')
    def test_all_assets_have_one_source_and_explicit_s75_qualification(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);self.fixtures(root);manifest=self.assemble(root)
            self.assertEqual(len(manifest['assets']),5)
            self.assertIn('physical qualification pending',manifest['qualification']['s75pro'])
            self.assertEqual(len((root/'SHA256SUMS').read_text().splitlines()),6)
    def test_missing_changed_or_different_commit_asset_is_rejected(self):
        for failure in ('missing','changed','commit','version'):
            with self.subTest(failure=failure),tempfile.TemporaryDirectory() as temporary:
                root=Path(temporary);self.fixtures(root);asset=root/release.ASSETS[0]
                if failure=='missing':asset.unlink()
                elif failure=='changed':asset.write_bytes(b'changed')
                else:
                    path=root/(asset.name+'.json');record=json.loads(path.read_text())
                    record['source_commit' if failure=='commit' else 'version']='wrong';path.write_text(json.dumps(record))
                with self.assertRaises((ValueError,FileNotFoundError)):self.assemble(root)
    def test_existing_public_release_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);self.fixtures(root)
            with patch.object(release,'head',return_value=COMMIT),patch.object(release,'version',return_value='0.2.0'),patch.dict('os.environ',GH_REPO='owner/repo'),patch.object(release.subprocess,'check_output',return_value='{"draft":false}'),patch.object(release.subprocess,'run') as mutate:
                with self.assertRaisesRegex(ValueError,'already public'):release.publish(root,COMMIT,'v0.2.0')
                mutate.assert_not_called()
    def test_assembly_requires_every_asset_and_rejects_changed_archives(self):
        with tempfile.TemporaryDirectory() as temporary,patch.object(release,'head',return_value=COMMIT),patch.object(release,'version',return_value='0.2.0'):
            root=Path(temporary);self.fixtures(root)
            manifest=release.assemble(root,COMMIT,'v0.2.0')
            self.assertEqual(len(manifest['assets']),5)
            self.assertIn('physical qualification pending',manifest['qualification']['s75pro'])
            self.assertEqual(len((root/'SHA256SUMS').read_text().splitlines()),6)
            asset=root/release.ASSETS[0];original=asset.read_bytes();asset.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'identity mismatch'):release.assemble(root,COMMIT,'v0.2.0')
            asset.write_bytes(original);asset.unlink()
            with self.assertRaises(FileNotFoundError):release.assemble(root,COMMIT,'v0.2.0')

    def test_tag_and_checked_out_commit_must_match(self):
        with patch.object(release,'head',return_value=COMMIT),patch.object(release,'version',return_value='0.2.0'):
            for commit,tag in [('b'*40,'v0.2.0'),(COMMIT,'v0.3.0')]:
                with self.assertRaises(ValueError):release.assemble(Path('.'),commit,tag)

if __name__=='__main__':unittest.main()
