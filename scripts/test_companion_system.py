#!/usr/bin/env python3
"""Exercise companion selection and bonus interruption in the linked ARM system."""
import argparse
import ctypes
import hashlib
import json
from pathlib import Path
from display_types import View
from serve_emulator import Emulator
from system_emulator import HOST


def run(image, output):
    emulator = Emulator(image)
    screenshots = []
    try:
        machine = emulator.machine
        # Keep the model awake while checking all four characters. This changes
        # modeled RAM only; idle-power qualification runs separately.
        machine.write(machine.symbols['state'] + 103, b'\x02')
        emulator.advance(3000)
        def view():
            return View.from_buffer_copy(machine.read(machine.symbols['frame'], ctypes.sizeof(View)))
        assert view().pet_character == 3
        hashes = set()
        for character in range(4):
            emulator.action('press')
            emulator.action('turn', -1)
            emulator.action('press')
            assert emulator.state()['page'] == 7
            assert bytes(view().rows[0]).startswith(b'Pet:')
            emulator.action('press')
            emulator.action('back'); emulator.action('back')
            assert emulator.state()['page'] == 0
            emulator.advance(300)
            assert view().pet_character == character
            filename = f'companion-{character}.png'
            emulator.frame.save(output.parent / filename)
            screenshots.append(filename)
            hashes.add(hashlib.sha256(emulator.frame.tobytes()).hexdigest())
        assert len(hashes) == 4
        # Bring the next real scheduler deadline into a short, controlled window.
        # Use the firmware clock bucket, not the host emulator's time origin.
        pet=machine.symbols['pet']
        machine.write32(pet+68,machine.read32(pet)+500)
        machine.write(pet+80,b'\0')
        emulator.advance(900)
        assert 6 <= view().pet_frame <= 11, {'error':'Idle bonus did not reach display','frame':view().pet_frame,'motion':bool(view().motion),'bonus':machine.read(pet+80,1).hex(),'bucket':machine.read32(pet),'due':machine.read32(pet+68),'host_ms':machine.read32(HOST+12)//1000}
        emulator.frame.save(output.parent / 'companion-bonus.png')
        emulator.action('tap', 'a')
        assert view().pet_frame in (2, 3), 'Typing did not interrupt the bonus'
        emulator.frame.save(output.parent / 'companion-typing.png')
        return dict(status='passed', candidate_sha256=hashlib.sha256(image.read_bytes()).hexdigest(),
                    hardware_writes=False, real_arm_image=True, screen_menu_reachable=True,
                    four_characters_selectable=True, distinct_rendered_characters=4,
                    idle_bonus_reaches_panel=True, typing_interrupts_bonus=True,
                    screenshots=screenshots + ['companion-bonus.png', 'companion-typing.png'])
    finally:
        emulator.machine.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('image', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = run(args.image, args.output)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))
