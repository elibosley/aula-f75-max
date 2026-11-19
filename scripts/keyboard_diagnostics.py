"""Collect a bounded, read-only USB report for a user-reviewed GitHub issue.

Never opens a HID device or requests bootloader entry, settings, key reports,
firmware, serial numbers, HID paths, or host/account identifiers.
"""
import datetime
import json
import platform
import sys
from pathlib import Path
from urllib.parse import urlencode

from keyboard_models import models

ROOT = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1]))
ISSUE_FORM = 'https://github.com/elibosley/aula-f75-max/issues/new'


def app_version():
    return json.loads((ROOT / 'package.json').read_text(encoding='utf-8'))['version']


def collect(devices):
    """Only publish allowlisted descriptor fields and recognized product strings."""
    known_names = {name: item['id'] for item in models() for name in item['usb']['product_names']}
    interfaces = []
    for device in devices:
        if (device.get('vendor_id'), device.get('product_id')) != (0x0c45, 0x800a):
            continue
        # Do not forward arbitrary device strings. They can contain personal labels.
        product = device.get('product_string')
        recognized = product in known_names
        row = dict(vendor_id='0c45', product_id='800a',
                   product=product if recognized else 'unrecognized product string',
                   model=known_names[product] if recognized else None)
        for field in ('release_number', 'usage_page', 'usage', 'interface_number'):
            value = device.get(field)
            if type(value) is int and -1 <= value <= 65535:
                row[field] = value
        interfaces.append(row)
        if len(interfaces) >= 32:
            break
    os_name = platform.system()
    return dict(schema=1, kind='s75-usb-diagnostics', app_version=app_version(),
                collected_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                operating_system=os_name if os_name in ('Darwin', 'Windows', 'Linux') else 'Other',
                usb_interfaces=interfaces,
                s75_detected=any(row['model'] == 's75pro' for row in interfaces),
                qualification='Physical S75 recovery, display, radio and charging validation pending.',
                installer_enabled=False,
                scope='USB enumeration only; no device opened or firmware changed.',
                excluded='No serial numbers, HID paths, key input, settings, firmware dumps or host/account identifiers.')


def issue_url(report):
    # Caller supplies the locally collected, allowlisted report, never arbitrary logs.
    body = ('## S75 Pro hardware diagnostics\n\n'
            'Please describe your keyboard revision and what you observed:\n\n'
            '- Keyboard revision / product link:\n- Screen and USB behavior:\n\n'
            'This report does not qualify the hardware or enable firmware installation.\n\n'
            '```json\n' + json.dumps(report, indent=2, ensure_ascii=True) + '\n```\n')
    return ISSUE_FORM + '?' + urlencode(dict(title='S75 Pro hardware diagnostics', body=body))
