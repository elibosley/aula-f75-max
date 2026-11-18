"""Native window behavior without starting a GUI or accessing a keyboard."""
from pathlib import Path
import sys
import types
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from desktop import DesktopState, keyboard_menu


class DesktopShellTest(unittest.TestCase):
    def test_only_unsaved_work_requires_close_confirmation(self):
        state = DesktopState()
        state._window = types.SimpleNamespace(confirm_close=False)
        for pending in (True, False, True):
            state.set_pending(pending)
            self.assertIs(state._window.confirm_close, pending)
        with self.assertRaises(ValueError):
            state.set_pending('false')

    def test_firmware_install_keeps_close_confirmation_during_settings_updates(self):
        state = DesktopState()
        state._window = types.SimpleNamespace(confirm_close=False)
        state.installer.update(busy=True)
        state.set_pending(False)
        self.assertTrue(state._window.confirm_close)
        state.installer.update(busy=False)
        state.firmware_install_status()
        self.assertFalse(state._window.confirm_close)

    def test_native_menu_uses_the_same_guarded_editor_commands(self):
        calls = []
        menu = keyboard_menu(types.SimpleNamespace(evaluate_js=calls.append, load_url=calls.append), 'http://127.0.0.1:1234')[0]
        actions = [item for item in menu.items if hasattr(item, 'function')]
        for item in actions:
            item.function()
        self.assertEqual(calls[:2], ['window.F75Studio?.reload()', 'window.F75Studio?.clock()'])
        self.assertEqual(calls[2], 'http://127.0.0.1:1234/firmware.html')
        self.assertEqual(len(actions), 10)
        self.assertEqual(calls[-1], 'window.F75Studio?.navigate("status")')


if __name__ == '__main__':
    unittest.main()
