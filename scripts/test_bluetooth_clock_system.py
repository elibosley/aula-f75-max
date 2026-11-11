#!/usr/bin/env python3
"""Verify Bluetooth clock RPC through linked ARM UART, timekeeping and Home."""
import argparse
import json
from pathlib import Path
from test_bluetooth_settings_system import run

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('image', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = run(args.image, clock_only=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))
