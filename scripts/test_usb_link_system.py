"""Lose SOF progress while keeping the configured driver state, then resume it."""
import argparse
import hashlib
import json
from pathlib import Path
from system_emulator import System, USB
from test_system_emulator import enumerate_usb


def run(image):
    with System(image) as machine:
        enumerate_usb(machine)

        def snapshot():
            machine.endpoint_out(3, b'F75bsof!' + bytes(24))
            machine.advance(10); machine.pump()
            reply = machine.endpoint_in(2)
            assert reply and reply[:8] == b'F75csof!'
            return reply[9]

        assert snapshot() & 8, 'Advancing host SOFs did not establish live USB'
        # The model already advances FRMNO only while this USB enable bit is
        # set. Gating it freezes SOF reception without changing ChibiOS state.
        # Diagnostic tokens remain a model-only observation channel here.
        config = machine.read32(USB + 0x10)
        machine.write32(USB + 0x10, config & ~(1 << 29))
        frame = machine.read32(USB + 0x60)
        machine.advance(150); machine.pump()
        assert machine.read32(USB + 0x60) == frame
        assert machine.read(machine.symbols['USBD1'], 1) == b'\4'
        assert not snapshot() & 8, 'Cached configured state falsely reported USB power'
        machine.advance(1000); machine.pump()
        assert not snapshot() & 8, 'Metadata traffic renewed stale USB evidence'
        machine.write32(USB + 0x10, config)
        machine.advance(10); machine.pump()
        assert snapshot() & 8, 'Resumed SOFs did not restore live USB'
        assert machine.read(machine.symbols['USBD1'], 1) == b'\4'
    return dict(status='passed', candidate_sha256=hashlib.sha256(image.read_bytes()).hexdigest(),
                configured_state_preserved_during_sof_stall=True,
                stale_power_clears_within_150_ms=True, metadata_cannot_refresh_sof_evidence=True,
                sof_resume_restores_power=True, model_changed=False, hardware_tested=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('image', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = run(args.image)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))
