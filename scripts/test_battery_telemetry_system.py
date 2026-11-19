#!/usr/bin/env python3
"""Read-only power RPC through actual linked ARM UART and its qualified carrier."""
import argparse
import json
from pathlib import Path
from test_bluetooth_settings_system import run

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('image',type=Path);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();result=run(a.image,power_only=True)
    a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
