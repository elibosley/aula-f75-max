#!/usr/bin/env python3
"""Compile and run the portable C tests without accessing hardware."""
from pathlib import Path
import subprocess,sys
ROOT=Path(__file__).resolve().parents[1]
out=ROOT/'analysis/portable-tests';out.mkdir(parents=True,exist_ok=True)
sources=sorted(str(p) for p in (ROOT/'firmware').glob('f75_*.c'))
for test in sorted((ROOT/'firmware').glob('test_*.c')):
 target=out/test.stem
 subprocess.run(['cc','-std=c11','-O2','-Wall','-Wextra','-Werror',str(test),*sources,'-o',str(target)],check=True,cwd=ROOT)
 subprocess.run([str(target)]+([str(out/'display.ppm')] if test.stem=='test_display' else []),check=True,cwd=ROOT)
print('All portable C tests passed.')
