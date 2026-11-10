"""Clean-checkout extraction keeps tar safety and never publishes partial trees."""
import importlib.util
import io
from pathlib import Path
import tarfile
import tempfile
import unittest

spec = importlib.util.spec_from_file_location(
    'bootstrap_emulator', Path(__file__).resolve().parents[1] / 'scripts/bootstrap_emulator.py')
bootstrap = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bootstrap)


class SourceExtractionTest(unittest.TestCase):
    def archive(self, root, link_name, target):
        path = root / 'source.tar'
        with tarfile.open(path, 'w') as stream:
            file = tarfile.TarInfo(f'qemu-{bootstrap.VERSION}/configure')
            file.size = 2
            stream.addfile(file, io.BytesIO(b'ok'))
            link = tarfile.TarInfo(link_name)
            link.type = tarfile.SYMTYPE
            link.linkname = target
            stream.addfile(link)
        return path

    def test_pinned_unused_link_is_omitted(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = self.archive(root, f'qemu-{bootstrap.VERSION}/roms/edk2/EmulatorPkg/Unix/Host/X11IncludeHack', '/opt/X11/include')
            bootstrap.extract_source(archive, root)
            self.assertEqual((root / f'qemu-{bootstrap.VERSION}/configure').read_bytes(), b'ok')
            self.assertFalse((root / f'qemu-{bootstrap.VERSION}/roms/edk2/EmulatorPkg/Unix/Host/X11IncludeHack').is_symlink())

    def test_other_absolute_and_escaping_links_fail_without_partial_source(self):
        for target in ['/opt/unexpected', '../../outside']:
            with self.subTest(target=target), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                archive = self.archive(root, f'qemu-{bootstrap.VERSION}/bad-link', target)
                with self.assertRaises(tarfile.FilterError):
                    bootstrap.extract_source(archive, root)
                self.assertFalse((root / f'qemu-{bootstrap.VERSION}').exists())
                self.assertEqual(list(root.glob('.qemu-extract-*')), [])


if __name__ == '__main__':
    unittest.main()
