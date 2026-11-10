#!/usr/bin/env python3
"""Send temporary home-screen text over the F75 USB settings interface."""
import argparse
import json

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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='operation', required=True)
    commands.add_parser('info')
    commands.add_parser('clear')
    send = commands.add_parser('set')
    send.add_argument('text')
    send.add_argument('--seconds', type=int, default=20)
    arguments = parser.parse_args()
    try:
        with Keyboard() as keyboard:
            result = display(keyboard, arguments.operation, getattr(arguments, 'text', ''),
                             getattr(arguments, 'seconds', 20))
        if not result['supported']:
            parser.exit(1, 'Install firmware with computer status support.\n')
    except (OSError, RuntimeError, ValueError) as error:
        parser.exit(1, f'{error}\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
