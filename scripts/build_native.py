#!/usr/bin/env python3
"""Build the native C preview library without touching a keyboard."""
from pathlib import Path
import os,subprocess,sys
ROOT=Path(__file__).resolve().parents[1]
(ROOT/'analysis').mkdir(exist_ok=True)
subprocess.run(['cc','-dynamiclib','-std=c11','-O2','-Wall','-Wextra','-Werror',*map(str,(ROOT/'firmware').glob('f75_*.c')),'-o',str(ROOT/'analysis/.libf75-new.dylib')],check=True)

os.replace(ROOT/'analysis/.libf75-new.dylib',ROOT/'analysis/libf75.dylib')
