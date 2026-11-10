#!/usr/bin/env python3
"""Package original keyboard companions without changing or opening the keyboard."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import zipfile
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
CHARACTERS = [
    ('keyboard-dog', 'Mochi', 'A little keyboard dog with very busy paws.'),
    ('little-robot', 'Pip', 'A mint robot with bright eyes and mitten hands.'),
    ('anime-guy', 'Ren', 'A cozy anime guy in a blue cardigan.'),
    ('starlight', 'Lumi', 'Your original lavender-haired desk companion.'),
]


def package_character(dest, source, bonus_source, slug, name):
    contents = {p.name: p.read_bytes() for p in sorted(dest.iterdir())
                if p.is_file() and p.suffix != '.zip'}
    contents['source-atlas.png'] = source.read_bytes()
    contents['bonus-atlas.png'] = bonus_source.read_bytes()
    prompts = json.loads((ROOT / 'assets/characters/generation-prompts.json').read_text())
    if slug in prompts['characters']:
        contents['generation-prompt.txt'] = prompts['characters'][slug].encode()
    bonus_prompts = json.loads((ROOT / 'assets/characters/bonus-generation-prompts.json').read_text())
    contents['bonus-generation-prompt.txt'] = bonus_prompts['characters'][slug].encode()
    contents['README.txt'] = (
        f'{name} / F75 Max companion pack\n\n'
        'Twelve 80x80 RGB565 frames with transparent color 0000.\n'
        'Byte order: little endian. Frame order is in manifest.json.\n'
        'pet_assets.h contains only the original six poses and uses the existing renderer names and sizes.\n'
        'The integrated firmware bank supports all four characters and twelve poses each.\n'
        'It replaces the single compiled character; do not add all headers together.\n'
        'A firmware rebuild, standard validation and guarded installation are required.\n'
        'This ZIP is artwork and source data, not a flashable keyboard image.\n'
        'Live character upload is not implemented. Never send this data to the radio.\n'
    ).encode()
    contents['SHA256SUMS'] = ''.join(
        f'{hashlib.sha256(data).hexdigest()}  {filename}\n'
        for filename, data in sorted(contents.items())).encode()
    archive = dest / f'{slug}.zip'
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as package:
        for filename, data in sorted(contents.items()):
            info = zipfile.ZipInfo(filename, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            package.writestr(info, data)
    return hashlib.sha256(archive.read_bytes()).hexdigest()


def main():
    library = ROOT / 'ui/assets/characters'
    library.mkdir(parents=True, exist_ok=True)
    entries = []
    work = []
    for slug, name, description in CHARACTERS:
        source = ROOT / ('assets/chibi/chibi-atlas-original.png' if slug == 'starlight'
                         else f'assets/characters/{slug}/source-atlas.png')
        dest = library / slug
        subprocess.run([sys.executable, str(ROOT / 'scripts/build_pet_assets.py'),
                        '--source', str(source), '--output', str(dest)], check=True)
        manifest = json.loads((dest / 'manifest.json').read_text())
        bonus_source = ROOT / f'assets/characters/{slug}/bonus-atlas.png'
        bonus_dir = ROOT / f'analysis/character-bonus/{slug}'
        subprocess.run([sys.executable, str(ROOT / 'scripts/build_pet_assets.py'),
                        '--source', str(bonus_source), '--output', str(bonus_dir)], check=True)
        bonus_names = ['sip-lift', 'sip', 'stretch-ready', 'stretch', 'groove-left', 'groove-right']
        for old, new in zip(manifest['frames'], bonus_names):
            (dest / (new + '.png')).write_bytes((bonus_dir / (old + '.png')).read_bytes())
        combined = Image.new('RGBA', (240, 320))
        combined.paste(Image.open(dest / 'sprites-80.png'), (0, 0))
        combined.paste(Image.open(bonus_dir / 'sprites-80.png'), (0, 160))
        combined.save(dest / 'sprites-80.png')
        (dest / 'frames.rgb565').write_bytes((dest / 'frames.rgb565').read_bytes() +
                                            (bonus_dir / 'frames.rgb565').read_bytes())
        manifest.update(frames=manifest['frames'] + bonus_names, native_rgb565_storage_bytes=153600,
                        native_grid=[3, 4], compiled_header_frames=6,
                        rgb565_layout='twelve row-major 80x80 frames in frame order',
                        bonus_source_sha256=hashlib.sha256(bonus_source.read_bytes()).hexdigest())
        manifest.update(id=slug, name=name, description=description,
                        source='Original AI-generated artwork; built-in image_gen',
                        animation={
                            'idle': {'frames': [0, 1, 0], 'durations_ms': [2700, 160, 700]},
                            'typing': {'frames': [2, 3], 'durations_ms': [180, 180]},
                            'flow': {'frames': [2, 3], 'durations_ms': [120, 120]},
                            'zoom': {'frames': [2, 3], 'durations_ms': [85, 85]},
                            'cheer': {'frames': [4], 'durations_ms': [700]},
                            'sleep': {'frames': [5], 'durations_ms': [1200]},
                            'reduced_motion': {'frames': [0], 'durations_ms': [1000]},
                            'sip': {'frames': [6, 7, 6, 0], 'durations_ms': [350, 1300, 350, 300]},
                            'stretch': {'frames': [8, 9, 8, 0], 'durations_ms': [350, 1100, 350, 300]},
                            'music': {'frames': [10, 11, 10, 11, 10, 11, 0], 'durations_ms': [240, 240, 240, 240, 240, 240, 300]},
                            'streak': {'frames': [4, 0, 4, 0], 'durations_ms': [350, 150, 350, 250]},
                        },
                        firmware_motion_note='Typing frame order and timing match f75_pet.c. '
                        'The firmware also adds a one-pixel bob and occasional cheer/effects.',
                        random_idle=dict(first_delay_ms=[6000, 12000], cooldown_ms=[12000, 28000],
                                         after_typing_delay_ms=[5000, 11000],
                                         clips=['sip', 'stretch', 'music'], immediate_repeat=False,
                                         typing_interrupts=True),
                        deployment='Firmware source integrates the four-character bank and bonus scenes; a validated build and guarded installation are required. Live sprite upload is not implemented.')
        (dest / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
        entries.append(dict(id=slug, name=name, description=description,
                            manifest=f'assets/characters/{slug}/manifest.json',
                            atlas=f'assets/characters/{slug}/firmware-sprites-80.png',
                            download=f'assets/characters/{slug}/{slug}.zip',
                            sha256=None))
        work.append((dest, source, bonus_source, slug, name))
    from build_companion_bank import main as build_bank
    build_bank()
    for entry, arguments in zip(entries, work):
        entry['sha256'] = package_character(*arguments)
    (library / 'index.json').write_text(json.dumps(dict(characters=entries), indent=2) + '\n')
    bundle = library / 'f75-companions.zip'
    with zipfile.ZipFile(bundle, 'w', compression=zipfile.ZIP_DEFLATED) as package:
        for entry in entries:
            path = ROOT / 'ui' / entry['download']
            info = zipfile.ZipInfo(path.name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED
            info.external_attr = 0o100644 << 16
            package.writestr(info, path.read_bytes())
    print(f'Packaged {len(entries)} companions; no firmware or settings written.')


if __name__ == '__main__':
    main()
