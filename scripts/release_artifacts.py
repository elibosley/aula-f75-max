#!/usr/bin/env python3
"""Bind release assets to one commit; publish only complete draft releases."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import zipfile

ROOT=Path(__file__).resolve().parents[1]
ASSETS=('F75-Studio-macos-arm64.zip','F75-Studio-windows-x64.zip',
        'F75-Studio-linux-x64.tar.gz','F75-Studio-firmware-f75max.zip',
        'F75-Studio-firmware-s75pro.zip')


def sha(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def version():return json.loads((ROOT/'package.json').read_text())['version']


def head():return subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()


def clean_worktree():
    if subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True).strip():
        raise ValueError('Commit source changes before packaging release artifacts')


def stamp(asset):
    asset=Path(asset)
    if asset.name not in ASSETS or not asset.is_file() or not asset.stat().st_size:
        raise ValueError('Missing or unknown release asset')
    clean_worktree()
    record=dict(file=asset.name,sha256=sha(asset),bytes=asset.stat().st_size,
                source_commit=head(),version=version())
    asset.with_name(asset.name+'.json').write_text(json.dumps(record,indent=2)+'\n')
    return record


def assemble(directory,commit,tag):
    directory=Path(directory)
    if not re.fullmatch('[0-9a-f]{40}',commit) or head()!=commit:
        raise ValueError('Release requires the exact checked-out commit SHA')
    if tag!='v'+version():raise ValueError('Release tag does not match the source version')
    records=[]
    for name in ASSETS:
        asset=directory/name
        record=json.loads(asset.with_name(name+'.json').read_text())
        if (record.get('file')!=name or record.get('source_commit')!=commit or
                record.get('version')!=version() or record.get('bytes')!=asset.stat().st_size or
                record.get('sha256')!=sha(asset)):
            raise ValueError('Release asset identity mismatch: '+name)
        if name.startswith('F75-Studio-firmware-'):
            target=name.removeprefix('F75-Studio-firmware-').removesuffix('.zip')
            with zipfile.ZipFile(asset) as archive:
                source=json.loads(archive.read('SOURCE.json'))
                proof=json.loads(archive.read('verification.json'))
                if source.get('commit')!=commit or source.get('target')!=target:
                    raise ValueError('Firmware corresponding source identity mismatch')
                if proof.get('status')!='passed' or proof.get('target')!=target or proof.get('source_commit')!=commit:
                    raise ValueError('Firmware verification did not pass')
                if 'corresponding-source.tar.gz' not in archive.namelist():
                    raise ValueError('Firmware corresponding source is missing')
                expected_profiles={'full_ui'} if target=='s75pro' else {'full_ui','usb_only'}
                if set(proof.get('profiles',{}))!=expected_profiles:
                    raise ValueError('Firmware profile proof is incomplete')
                for profile,check in proof['profiles'].items():
                    if check.get('status')!='passed' or check.get('identical_clean_builds')!=2:
                        raise ValueError('Firmware reproducibility did not pass')
                    for suffix in ('bin','elf'):
                        binary=archive.read(f'{profile}/{target}-wired-test.{suffix}')
                        if hashlib.sha256(binary).hexdigest()!=check['sha256'][suffix]:
                            raise ValueError('Firmware bytes differ from the tested '+suffix)
        records.append(record)
    manifest=dict(version=version(),tag=tag,source_commit=commit,assets=records,
                  qualification={'f75max':'development board; exact candidate emulation tested',
                                 's75pro':'experimental; emulation tested; physical qualification pending'})
    path=directory/'release-manifest.json';path.write_text(json.dumps(manifest,indent=2)+'\n')
    files=[directory/name for name in ASSETS]+[path]
    (directory/'SHA256SUMS').write_text(''.join(sha(p)+'  '+p.name+'\n' for p in files))
    return manifest


def find_release(repo,tag):
    # The tag endpoint only returns published releases. The authenticated list
    # includes drafts, including those that do not have a Git tag yet.
    pages=json.loads(subprocess.check_output(
        ['gh','api','--paginate','--slurp',f'repos/{repo}/releases?per_page=100'],text=True))
    matches=[release for page in pages for release in page if release.get('tag_name')==tag]
    if len(matches)!=1:raise ValueError('Expected exactly one release for '+tag)
    return matches[0]


def publish(directory,commit,tag):
    manifest=assemble(directory,commit,tag)
    repo=os.environ['GH_REPO']
    if not re.fullmatch(r'[\w.-]+/[\w.-]+',repo):raise ValueError('Invalid release repository')
    release=find_release(repo,tag)
    if not release['draft']:
        raise ValueError('Release is already public; its assets will not be overwritten')
    # A draft may not have a Git tag yet. If a tag exists, it must resolve to
    # this source. Never move an existing tag to repair a release mismatch.
    result=subprocess.run(['gh','api',f'repos/{repo}/git/ref/tags/{tag}'],text=True,capture_output=True)
    if result.returncode==0:
        ref=json.loads(result.stdout)['object']
        for _ in range(8):
            if ref['type']=='commit':break
            if ref['type']!='tag':raise ValueError('Unsupported release tag type')
            ref=json.loads(subprocess.check_output(['gh','api',f'repos/{repo}/git/tags/{ref["sha"]}'],text=True))['object']
        if ref['type']!='commit' or ref['sha']!=commit:
            raise ValueError('Existing release tag points to another commit')
    elif 'HTTP 404' not in result.stderr:
        raise RuntimeError('Could not verify the existing release tag')
    files=[str(Path(directory)/name) for name in ASSETS]+[str(Path(directory)/name) for name in ('release-manifest.json','SHA256SUMS')]
    subprocess.run(['gh','release','edit',tag,'--repo',repo,'--target',commit,'--draft=true'],check=True)
    subprocess.run(['gh','release','upload',tag,*files,'--repo',repo,'--clobber'],check=True)
    # Verify GitHub's stored bytes before making the draft public.
    uploaded=json.loads(subprocess.check_output(['gh','api',f'repos/{repo}/releases/{release["id"]}/assets'],text=True))
    by_name={item['name']:item for item in uploaded}
    for file in files:
        path=Path(file);remote=by_name.get(path.name,{})
        if remote.get('size')!=path.stat().st_size or remote.get('digest')!='sha256:'+sha(path):
            raise ValueError('Uploaded asset verification failed: '+path.name)
    note=Path(directory)/'release-notes.md'
    notes=(release.get('body') or '')+'\n\n### Downloads\n\n'
    notes+='Desktop: macOS Apple Silicon, Windows x64 and Linux x64 archives. Firmware: separate F75 Max and S75 Pro archives, including corresponding source, build metadata and test receipts. Verify downloads with SHA256SUMS.\n\n'
    notes+='S75 Pro firmware is experimental and has not been tested on physical hardware. One-click S75 installation remains unavailable pending hardware qualification. These firmware downloads are development candidates.\n'
    note.write_text(notes)
    subprocess.run(['gh','release','edit',tag,'--repo',repo,'--target',commit,'--notes-file',str(note),
                    '--draft=false','--prerelease=true','--latest=false'],check=True)
    actual=subprocess.check_output(['gh','api',f'repos/{repo}/commits/{tag}','--jq','.sha'],text=True).strip()
    if actual!=commit:raise ValueError('Published tag does not match the built source')
    print('Published verified artifacts for '+manifest['tag'])


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    commands=parser.add_subparsers(dest='command',required=True)
    command=commands.add_parser('stamp');command.add_argument('--asset',type=Path,required=True)
    for name in ('assemble','publish'):
        command=commands.add_parser(name);command.add_argument('--directory',type=Path,required=True)
        command.add_argument('--commit',required=True);command.add_argument('--tag',required=True)
    args=parser.parse_args()
    if args.command=='stamp':stamp(args.asset)
    elif args.command=='assemble':assemble(args.directory,args.commit,args.tag)
    else:publish(args.directory,args.commit,args.tag)
