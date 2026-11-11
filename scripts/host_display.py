#!/usr/bin/env python3
"""Send a temporary notification to the F75 Home screen."""
import argparse
import json
import subprocess
from pathlib import Path

from keyboard_customize import Keyboard


def payload(operation, text='', seconds=20):
    if operation == 'set':
        if not isinstance(text, str) or not text.strip() or not 1 <= len(text) <= 20:
            raise ValueError('Enter 1 to 20 printable characters.')
        if any(not 32 <= ord(character) <= 126 for character in text):
            raise ValueError('Use printable ASCII letters, numbers, and punctuation.')
        if type(seconds) is not int or not 1 <= seconds <= 60:
            raise ValueError('Choose a duration from 1 to 60 seconds.')
        return bytes((1, 1, seconds, len(text))) + text.encode('ascii').ljust(20, b'\0')
    return bytes((1, {'info': 0, 'clear': 2}[operation])) + bytes(22)


def display(keyboard, operation, text='', seconds=20):
    request = payload(operation, text, seconds)
    health = keyboard.raw_request(b'F75?')
    if health[:4] != b'F75!' or not health[24] & 16:
        return {'supported': False, 'ready': False, 'active': False}
    reply = keyboard.raw_request(b'F75y', request)
    if reply[:4] != b'F75a' or reply[8] != 1:
        raise RuntimeError('Unexpected keyboard display reply.')
    if reply[9] == 2:
        raise RuntimeError('Select USB on the keyboard to show computer status.')
    if reply[9] != 0:
        raise RuntimeError('The keyboard rejected the display request.')
    return {'supported': True, 'ready': bool(reply[10]), 'active': bool(reply[11])}


def bluetooth_access(probe, request=False):
    """Inspect access, or request it only after an explicit desktop action."""
    command = '--request-access' if request else '--check'
    try:
        completed = subprocess.run([str(probe), command], capture_output=True,
                                   text=True, timeout=10)
        result = json.loads(completed.stdout)
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError) as error:
        raise RuntimeError('Could not check Mac Input Monitoring access.') from error
    if completed.returncode or not isinstance(result, dict):
        raise RuntimeError('Could not check Mac Input Monitoring access.')
    access = result.get('access')
    if access not in ('granted', 'denied', 'unknown'):
        raise RuntimeError('The Bluetooth helper returned an unknown access state.')
    return {'access': access, 'permission_requested': result.get('permission_requested') is True}


def bluetooth_display(probe, operation, text='', seconds=20):
    request = payload(operation, text, seconds)
    arguments = {'info': ('--status-info',), 'clear': ('--clear-status',)}
    command = ('--status', request[4:4 + request[3]].decode('ascii'),
               str(request[2])) if operation == 'set' else arguments[operation]
    try:
        result = subprocess.run([str(probe), *command], capture_output=True, text=True, timeout=30)
    except subprocess.TimeoutExpired as error:
        raise RuntimeError('Bluetooth status timed out. Check the keyboard and try again.') from error
    except OSError as error:
        raise RuntimeError('Could not start the Bluetooth status helper.') from error
    try:
        reply = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        if 'Enroll this keyboard' in result.stderr:
            raise RuntimeError('Enroll this keyboard with the USB host helper first.') from error
        raise RuntimeError('The Bluetooth status helper returned an invalid reply.') from error
    if not isinstance(reply, dict):
        raise RuntimeError('The Bluetooth status helper returned an invalid reply.')
    if reply.get('access') != 'granted':
        raise RuntimeError('Allow F75 Studio in System Settings > Privacy & Security > Input Monitoring, then quit and reopen Studio.')
    if not reply.get('open_attempted'):
        raise RuntimeError('Connect one enrolled F75 Max Bluetooth slot and check again.')
    if reply.get('open_status') != '0x00000000':
        raise RuntimeError('The Mac could not open the Bluetooth keyboard. Check that the Mac is unlocked.')
    if reply.get('display_transport') == 'Report descriptor mismatch':
        raise RuntimeError('This keyboard’s Bluetooth report format is unsupported.')
    if reply.get('display_led_read_status') != '0x00000000':
        raise RuntimeError('Unlock the Mac and wake the keyboard, then check the connection again.')
    field = 'display_ready' if operation == 'info' else 'display_reports_written'
    if result.returncode or reply.get(field) is not True:
        raise RuntimeError('The Mac could not finish the Bluetooth status request. Check the keyboard before retrying.')
    return {'supported': True, 'ready': True, 'transport': 'bluetooth',
            'reports_written': operation != 'info'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--transport', choices=('usb', 'bluetooth'), default='usb')
    parser.add_argument('--probe', type=Path,
                        help='Enrolled native Bluetooth helper executable (macOS preview)')
    commands = parser.add_subparsers(dest='operation', required=True)
    commands.add_parser('info')
    commands.add_parser('clear')
    send = commands.add_parser('set', aliases=['notify'])
    send.add_argument('text')
    send.add_argument('--seconds', type=int, default=20)
    arguments = parser.parse_args()
    try:
        operation = 'set' if arguments.operation == 'notify' else arguments.operation
        fields = (operation, getattr(arguments, 'text', ''), getattr(arguments, 'seconds', 20))
        if arguments.transport == 'bluetooth':
            if arguments.probe is None:
                raise ValueError('Choose the enrolled Bluetooth helper with --probe.')
            result = bluetooth_display(arguments.probe, *fields)
        else:
            with Keyboard() as keyboard:
                result = display(keyboard, *fields)
        if not result['supported']:
            parser.exit(1, 'Install firmware with computer status support.\n')
    except (OSError, RuntimeError, ValueError) as error:
        parser.exit(1, f'{error}\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
