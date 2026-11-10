#!/usr/bin/env python3
"""Package only canonical firmware and sanitized verification receipts."""
import hashlib,json,shutil,subprocess,io,tarfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
latest=json.loads((ROOT/'analysis/repro/latest.json').read_text())
receipt=json.loads((ROOT/latest['receipt']).read_text())
assert receipt['status']=='passed'
out=ROOT/'dist';out.mkdir(exist_ok=True)
def source_metadata(entry):
 entry.uid=entry.gid=0;entry.uname=entry.gname='';entry.mtime=0
 return entry
for profile,record in receipt['profiles'].items():
 assert record['status']=='passed' and record['identical_clean_builds']==2
 source=(ROOT/record['system_receipt']).parent;target=out/profile;target.mkdir(exist_ok=True)
 for extension in ['bin','elf','map','json']:
  src=source/('f75max-wired-test.'+extension);dst=target/src.name
  if extension in ['bin','elf']:shutil.copy2(src,dst)
  elif extension=='json':
   metadata=json.loads(src.read_text());metadata.pop('flash_authorized_by_user',None)
   dst.write_text(json.dumps(metadata,indent=2).replace(str(ROOT),'<checkout>')+'\n')
  else:dst.write_text(src.read_text().replace(str(ROOT),'<checkout>'))
 (target/'build-inputs.json').write_bytes((source/'build-inputs.json').read_bytes())
 for src in source.glob('*-tests.json'):(target/src.name).write_text(src.read_text().replace(str(ROOT),'<checkout>'))
(out/'verification.json').write_text(json.dumps(receipt,indent=2).replace(str(ROOT),'<checkout>')+'\n')
# Include exact corresponding project/dependency sources alongside binaries.
project=subprocess.check_output(['git','archive','--format=tar','HEAD'],cwd=ROOT)
with tarfile.open(out/'corresponding-source.tar.gz','w:gz') as bundle:
 with tarfile.open(fileobj=io.BytesIO(project)) as own:
  for entry in own:
   entry.name='aula-f75-max-source/'+entry.name
   bundle.addfile(source_metadata(entry),own.extractfile(entry) if entry.isfile() else None)
 for dependency in json.loads((ROOT/'firmware/targets/f75max/dependencies.json').read_text())['sources']:
  source=ROOT/'builddeps'/(dependency['name']+'.tar.gz')
  assert hashlib.sha256(source.read_bytes()).hexdigest()==dependency['archive_sha256']
  bundle.add(source,arcname='aula-f75-max-source/builddeps/'+source.name,recursive=False,filter=source_metadata)
(out/'SOURCE.json').write_text(json.dumps({'repository':'https://github.com/elibosley/aula-f75-max','commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'license':'GPL-2.0-or-later with separately licensed assets','scope':'Reproducible source-only builds; no physical hardware or captured factory ROM qualification'},indent=2)+'\n')
(out/'SHA256SUMS').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+str(p.relative_to(out))+'\n' for p in sorted(out.rglob('*')) if p.is_file() and p.name!='SHA256SUMS'))
print('Packaged canonical firmware and verification receipts in dist/.')
