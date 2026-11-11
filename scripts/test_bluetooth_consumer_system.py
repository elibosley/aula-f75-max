#!/usr/bin/env python3
"""Check keyboard/Fn semantics while the ARM adapter sends every data octet."""
import argparse,json
from pathlib import Path
from test_bluetooth_settings_system import run

if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('image',type=Path);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();result=run(a.image,consumer_only=True)
    a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
