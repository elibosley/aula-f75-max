"""Model metadata shared by desktop installation and display simulation."""
import json
import sys
from pathlib import Path

ROOT = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1]))


def models():
    s75 = json.loads((ROOT / 'firmware/targets/s75pro/model.json').read_text())
    return [dict(id='f75max', name='AULA F75 Max', display=dict(width=128, height=128),
                 usb=dict(vendor_id=0x0c45, product_id=0x800a,
                          product_names=['AULA F75 Max', 'AULA F75Max']),
                 firmware_port='development-board-tested', hardware_qualification='development board'), s75]


def model(identifier):
    for item in models():
        if item['id'] == identifier:
            return item
    raise ValueError('Unknown keyboard model')


def identify(devices):
    """Shared USB IDs cannot select a model without its exact product string."""
    found = {}
    for device in devices:
        for item in models():
            usb = item['usb']
            if (device.get('vendor_id'), device.get('product_id')) != (usb['vendor_id'], usb['product_id']):
                continue
            if device.get('product_string') not in usb['product_names']:
                continue
            # Multiple HID interfaces belong to one physical USB device.
            location = (device.get('serial_number') or '', device.get('product_string'))
            found[(item['id'], location)] = item['id']
    if len(found) != 1:
        raise ValueError('Connect one supported keyboard by USB. Its exact model must be identified.')
    return model(next(iter(found.values())))
