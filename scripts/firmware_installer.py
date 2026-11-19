"""Desktop USB installation of a bundled, model-qualified firmware release."""
import hashlib
import json
import sys
import os
from pathlib import Path
import threading
import time
import uuid

from flash_keyboard import Rom, program, verify_system_checks
from keyboard_models import identify, model
from keyboard_customize import hid_backend
from keyboard_transport_lock import TransportLock
from recovery_image import verify_recovery

ROOT = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1]))


def load_bundle(model_id, directory):
    target = model(model_id)
    directory = Path(directory)
    manifest = json.loads((directory / 'release.json').read_text())
    if manifest.get('target') != model_id or manifest.get('qualification') != 'passed':
        raise ValueError('This model has no qualified custom firmware release yet.')
    files = {}
    for name in ('firmware.bin', 'firmware.elf', 'build.json', 'adapter-tests.json', 'system-tests.json'):
        data = (directory / name).read_bytes()
        if hashlib.sha256(data).hexdigest() != manifest['sha256'].get(name):
            raise ValueError('Firmware package verification failed. Reinstall the complete Studio application.')
        files[name] = data
    image = files['firmware.bin']
    if len(image) != 262144 or image[-4:] != bytes.fromhex('5555aaaa'):
        raise ValueError('Firmware image size or validity flag is incorrect.')
    build = json.loads(files['build.json'])
    if build.get('target') != model_id or build.get('display') != {key: target['display'][key] for key in ('width', 'height')}:
        raise ValueError('Firmware was built for a different keyboard or screen.')
    verify_recovery(image, build, json.loads(files['adapter-tests.json']))
    verify_system_checks(image, files['firmware.elf'], build, json.loads(files['system-tests.json']),
                         require_factory_loader=False)
    # The release owner must name the supported original firmware checksums.
    checksums = manifest.get('stock_checksums', [])
    if not checksums or any(type(value) is not int or not 0 <= value <= 65535 for value in checksums):
        raise ValueError('Firmware release has no supported stock firmware versions.')
    return image, checksums


class FirmwareInstaller:
    def __init__(self, bundle_root=None, data_root=None):
        self.bundle_root = Path(bundle_root or ROOT / 'firmware/releases')
        self.data_root = Path(data_root or Path.home() / '.f75-studio/installations')
        self.lock = threading.Lock()
        self.state = dict(stage='idle', message='Connect your S75 Pro by USB.', busy=False)

    def snapshot(self):
        with self.lock:
            return dict(self.state)

    def update(self, **values):
        with self.lock:
            self.state.update(values)

    def availability(self):
        try:
            target = identify(hid_backend().enumerate(0x0c45, 0x800a))
            if target['id'] != 's75pro':
                raise ValueError('Connect an AULA S75 Pro by USB to install its firmware.')
            load_bundle(target['id'], self.bundle_root / target['id'])
            return dict(available=True, model=target['name'], message='Ready to install custom firmware. The keyboard will restart with default custom settings.')
        except FileNotFoundError:
            return dict(available=False, model='AULA S75 Pro', message='S75 Pro firmware builds and runs in emulation. Installation awaits physical recovery and hardware validation.')
        except (OSError, ValueError, KeyError) as error:
            return dict(available=False, message=str(error))

    def start(self):
        with self.lock:
            if self.state['busy']:
                return dict(self.state)
            self.state = dict(stage='checking', message='Checking the connected keyboard and firmware.', busy=True)
        worker = threading.Thread(target=self.install, daemon=False)
        worker.start()
        return self.snapshot()

    def install(self):
        rom = None
        receipt = dict(attempt=uuid.uuid4().hex, erase_requested=False, program_verified=False)
        path = None
        def save():
            self.update(stage=receipt.get('stage', 'checking'), bytes_written=receipt.get('bytes_written', 0))
            temporary = path.with_suffix('.tmp')
            descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os,'O_NOFOLLOW',0), 0o600)
            with os.fdopen(descriptor,'w') as output:
                json.dump(receipt, output, indent=2)
                output.flush()
                os.fsync(output.fileno())
            temporary.replace(path)
        try:
            self.data_root.mkdir(parents=True, exist_ok=True, mode=0o700)
            path = self.data_root / (receipt['attempt'] + '.json')
            with TransportLock(timeout=1):
                devices = hid_backend().enumerate(0x0c45, 0x800a)
                target = identify(devices)
                if target['id'] != 's75pro':
                    raise ValueError('The USB keyboard is not an S75 Pro.')
                image, stock_checksums = load_bundle('s75pro', self.bundle_root / 's75pro')
                # No raw flashing path is exposed for other models or arbitrary files.
                receipt.update(target=target['id'], image_sha256=hashlib.sha256(image).hexdigest(), stage='entering_bootloader')
                save()
                rom = Rom(0x0c45, 0x800a)
                rom.write(bytes.fromhex('aa42895aff7162cc') + bytes(56))
                time.sleep(.1)
                identity = rom.identify()
                current = rom.sum()
                receipt.update(identity_before=identity, checksum_before=current)
                save()
                if current not in stock_checksums:
                    raise ValueError('Installed firmware version is unrecognized. Installation stopped before erase.')
                self.update(message='Installing custom firmware. Keep the USB cable connected.')
                program(rom, image, current, receipt, save)
                receipt.update(stage='restarting', return_requested=True)
                save()
                rom.command(7)
                receipt['stage'] = 'programmed_return_requested'
                save()
            self.update(stage='complete', busy=False, message='Firmware programming and checksum verification completed. The keyboard is restarting.')
        except Exception as error:
            recovery = receipt['erase_requested']
            if rom is not None and not recovery:
                try:
                    rom.command(7)
                except Exception:
                    recovery = True
            receipt.update(stage='recovery_required' if recovery else 'failed_before_erase', error=str(error))
            if path is not None:
                save()
            self.update(busy=False, message=str(error), recovery_required=recovery)
        finally:
            if rom is not None:
                rom.close()
