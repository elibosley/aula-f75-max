"""Offline failure checks for the destructive programming path."""
import contextlib
import io
from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from flash_keyboard import Rom, checksum, program


IMAGE = bytes(60) + struct.pack('<I', 0xaaaa5555)


class SimulatedRom:
    def __init__(self, *, current=0x0e8e, dirty_erase=False, bad_program=False, implicit_unprotect=False):
        self.current = current; self.dirty_erase = dirty_erase; self.bad_program = bad_program
        self.implicit_unprotect = implicit_unprotect; self.security = 0x5a5a
        self.calls = []; self.data = bytearray()

    def identify(self):
        return dict(family=32, chip=5, revision=0, code_option=0xffff, security=self.security)

    def sum(self):
        return checksum(self.data) if self.data else self.current

    def command(self, opcode, fields=None):
        self.calls.append((opcode, fields))
        response = bytearray(64)
        if opcode == 4:
            self.current = 1 if self.dirty_erase else 0
            if self.implicit_unprotect: self.security = 0xffff
            struct.pack_into('<H', response, 8, self.current)
        elif opcode == 5:
            assert self.current == 0
        elif opcode == 3:
            assert dict((o, v) for o, f, v in fields) == {4: 0xffff, 6: 0x5a5a}
            self.security = 0x5a5a
        else:
            raise AssertionError(f'Unexpected destructive-path opcode: {opcode}')
        return bytes(response)

    def write(self, data):
        assert self.calls[-1][0] == 5 and len(data) == 64
        self.data.extend(data)

    def reply(self, opcode):
        assert opcode == 5
        response = bytearray(64)
        struct.pack_into('<H', response, 8, checksum(self.data) ^ int(self.bad_program))
        response[60:64] = self.data[-4:]
        return bytes(response)


class ProgrammingContract(unittest.TestCase):
    def execute(self, rom):
        record = dict(erase_requested=False, program_verified=False)
        with contextlib.redirect_stdout(io.StringIO()):
            program(rom, IMAGE, 0x0e8e, record, lambda: None)
        return record

    def test_changed_installed_checksum_never_erases(self):
        rom = SimulatedRom(current=0x1234)
        with self.assertRaisesRegex(RuntimeError, 'checksum changed'): self.execute(rom)
        self.assertEqual(rom.calls, [])

    def test_dirty_erase_never_enables_programming(self):
        rom = SimulatedRom(dirty_erase=True)
        with self.assertRaisesRegex(RuntimeError, 'Erase checksum'): self.execute(rom)
        self.assertEqual([op for op, fields in rom.calls], [4])

    def test_bad_program_never_restores_security_or_returns_to_user(self):
        rom = SimulatedRom(bad_program=True)
        with self.assertRaisesRegex(RuntimeError, 'checksum mismatch'): self.execute(rom)
        self.assertEqual([op for op, fields in rom.calls], [4, 5])

    def test_success_preserves_cs1_without_security_command(self):
        rom = SimulatedRom(); result = self.execute(rom)
        self.assertTrue(result['program_verified'])
        self.assertEqual([op for op, fields in rom.calls], [4, 5])
        self.assertEqual(result['identity_after']['security'], 0x5a5a)

    def test_implicit_unprotect_only_restores_original_protection(self):
        rom = SimulatedRom(implicit_unprotect=True); result = self.execute(rom)
        self.assertTrue(result['program_verified'])
        self.assertEqual([op for op, fields in rom.calls], [4, 5, 3])
        self.assertEqual(rom.security, 0x5a5a)

    def test_rom_echo_is_not_an_ack(self):
        class EchoBackend:
            def ctrl_transfer(self, h, bm, req, value, index, data, timeout):
                data[:4] = __import__('array').array('B', bytes.fromhex('01aa5500'))
                return 64
        rom = Rom.__new__(Rom); rom.backend = EchoBackend(); rom.handle = None
        with self.assertRaisesRegex(RuntimeError, 'Invalid ROM ACK'): rom.reply(1)

    def test_disabled_boot_options_are_rejected(self):
        rom = Rom.__new__(Rom)
        response = bytearray.fromhex('01aa5500fafafafa20050000faff5a5a') + bytearray(48)
        rom.command = lambda opcode: bytes(response)
        with self.assertRaisesRegex(RuntimeError, 'boot-pin'): rom.identify()


class SystemAdmissionContract(unittest.TestCase):
    def test_valid_image_requires_matching_real_arm_system_receipt(self):
        import hashlib
        from flash_keyboard import verify_system_checks
        image, elf = b'candidate', b'linked elf'
        build = {'profile': 'usb_only'}
        result = dict(status='passed', candidate_sha256=hashlib.sha256(image).hexdigest(),
                      elf_sha256=hashlib.sha256(elf).hexdigest(), profile='usb_only',
                      function_stubs=[], unmodeled_mmio_accesses=0,
                      clock_states={'valid_handoff_values_reach_main': list(range(16))},
                      usb={'configured': True}, factory_loader={'status':'passed'}, reset_recovery={'cases': [
                          dict(wheel_held=held, magic=magic, reached='rom_boundary' if held or magic else 'c_runtime')
                          for held, magic in [(False,False),(True,False),(False,True),(True,True)]]})
        verify_system_checks(image, elf, build, result)
        for field, changed in [('candidate_sha256', 'wrong'), ('elf_sha256', 'wrong'),
                               ('profile', 'full_ui'), ('status', 'failed'),
                               ('function_stubs', ['chSysInit']), ('unmodeled_mmio_accesses', 1),
                               ('reset_recovery', {}), ('clock_states', {}), ('usb', {})]:
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'complete ARM system checks'):
                verify_system_checks(image, elf, build, dict(result, **{field: changed}))


if __name__ == '__main__':
    unittest.main()
