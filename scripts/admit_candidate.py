#!/usr/bin/env python3
"""Archive and stage exact reproducible artifacts and their offline admission checks."""
import argparse,hashlib,json,shutil,tempfile
from pathlib import Path
from flash_keyboard import ROOT,load_candidate,checksum

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def admit(a,b,names):
 a=a.resolve();b=b.resolve();image=a/'f75max-wired-test.bin';identity=sha(image)
 for extension in ['bin','elf']:
  name='f75max-wired-test.'+extension
  if sha(a/name)!=sha(b/name):raise ValueError('Clean builds differ: '+extension)
 build=json.loads((a/'f75max-wired-test.json').read_text())
 for rel,expected in build['source_sha256'].items():
  if sha(ROOT/rel)!=expected:raise ValueError('Source changed since build: '+rel)
 checks=json.loads((a/'adapter-tests.json').read_text())
 if checks['candidate_sha256']!=identity:raise ValueError('Adapter receipt mismatch')
 for name in ['system']+names:
  r=json.loads((a/(name+'-tests.json')).read_text())
  if r.get('status')!='passed' or r['candidate_sha256']!=identity:raise ValueError(name+' receipt missing or failed')
 staged=ROOT/'analysis/UNFLASHED'
 for name in ['f75max-wired-test.bin','f75max-wired-test.elf','f75max-wired-test.map','f75max-wired-test.json','system-tests.json']:
  shutil.copy2(a/name,staged/name)
 shutil.copy2(a/'adapter-tests.json',ROOT/'analysis/keyboard-image-tests.json')
 payload=load_candidate(identity)
 parent=ROOT/'analysis/candidates';destination=parent/identity
 if destination.exists():
  if sha(destination/image.name)!=identity:raise ValueError('Existing archive differs')
 else:
  with tempfile.TemporaryDirectory(prefix='.admission-',dir=parent) as temp:
   draft=Path(temp)/identity;draft.mkdir()
   for source in a.iterdir():
    if source.is_file():shutil.copy2(source,draft/source.name)
   shutil.copytree(ROOT/'builddeps/qmk/keyboards/aula/f75max_test',draft/'board-source')
   shutil.copytree(ROOT/'scripts',draft/'scripts',ignore=shutil.ignore_patterns('__pycache__'))
   for source in [ROOT/'emulator/qemu/f75max.c',ROOT/'analysis/qemu-build.json']:shutil.copy2(source,draft/source.name)
   (draft/'reproducibility.json').write_text(json.dumps({'candidate_sha256':identity,'identical_clean_bin_elf_builds':2,'build_directories':[str(a.relative_to(ROOT)),str(b.relative_to(ROOT))],'protected_recovery_sha256':build['reset_recovery']['sha256'],'hardware_tested':False},indent=2)+'\n')
   draft.rename(destination)
 return {'admitted':identity,'checksum':f'{checksum(payload):04x}','archive':str(destination)}
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('a',type=Path);p.add_argument('b',type=Path);p.add_argument('--check',action='append',default=[]);x=p.parse_args();print(json.dumps(admit(x.a,x.b,x.check)))
