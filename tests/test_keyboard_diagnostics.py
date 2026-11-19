"""Diagnostic sharing must not disclose identifiers or unlock installation."""
import json
from pathlib import Path
import sys
import unittest
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from keyboard_diagnostics import collect, issue_url


class DiagnosticsTest(unittest.TestCase):
    def test_report_uses_only_allowed_descriptor_fields(self):
        report = collect([dict(vendor_id=0x0c45, product_id=0x800a,
            product_string='AULA-S75Pro', serial_number='private-serial',
            path=b'/private/device', manufacturer_string='private-name',
            interface_number=1, usage_page=0xff00, release_number=272,
            unexpected='private-extra')])
        encoded = json.dumps(report)
        self.assertNotIn('private-', encoded)
        self.assertNotIn('unexpected', encoded)
        self.assertTrue(report['s75_detected'])
        self.assertFalse(report['installer_enabled'])
        self.assertIn('pending', report['qualification'])
        self.assertEqual(report['usb_interfaces'][0]['usage_page'], 0xff00)

    def test_unknown_strings_and_unrelated_devices_never_leave_report(self):
        report = collect([dict(vendor_id=0x0c45, product_id=0x800a,
            product_string='Owner Name <script>bad</script>', usage='not-a-number'),
            dict(vendor_id=123, product_id=456, product_string='private-mouse')])
        self.assertFalse(report['s75_detected'])
        self.assertEqual(len(report['usb_interfaces']), 1)
        encoded = json.dumps(report)
        self.assertNotIn('Owner', encoded)
        self.assertNotIn('private-mouse', encoded)
        self.assertNotIn('not-a-number', encoded)

    def test_report_is_bounded_and_empty_detection_is_truthful(self):
        self.assertFalse(collect([])['s75_detected'])
        device = dict(vendor_id=0x0c45, product_id=0x800a, product_string='AULA-S75Pro')
        self.assertEqual(len(collect([device]*100)['usb_interfaces']), 32)

    def test_issue_is_a_fixed_destination_draft_with_reviewable_report(self):
        report = collect([])
        url = urlsplit(issue_url(report))
        self.assertEqual((url.scheme, url.netloc, url.path),
            ('https', 'github.com', '/elibosley/aula-f75-max/issues/new'))
        body = parse_qs(url.query)['body'][0]
        self.assertIn(json.dumps(report, indent=2), body)
        self.assertIn('does not qualify', body)

    def test_desktop_bridge_cannot_open_an_uncollected_or_injected_report(self):
        from desktop import DesktopState
        state = DesktopState()
        with self.assertRaisesRegex(ValueError, 'Collect and review'):
            state.open_s75_diagnostic_issue()
        with patch('desktop.hid_backend') as backend:
            backend.return_value.enumerate.return_value = []
            report = state.collect_s75_diagnostics()
        with patch('webbrowser.open', return_value=True) as browser:
            state.open_s75_diagnostic_issue()
        self.assertEqual(browser.call_args.args, (issue_url(report),))
        state.installer.update(busy=True)
        with self.assertRaisesRegex(ValueError, 'current keyboard operation'):
            state.collect_s75_diagnostics()
