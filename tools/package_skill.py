#!/usr/bin/env python3
"""Package only distributable Skill resources; never include local user media."""
from pathlib import Path
import hashlib
import json
import re
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / 'skills/tennisprism'
ALLOWED = {'.md', '.py', '.json', '.yaml', '.html', '.js', '.css', '.txt'}

def main():
    front = (SKILL / 'SKILL.md').read_text(encoding='utf-8')
    version = re.search(r'\bversion:\s*"([0-9.]+)"', front).group(1)
    files = []
    for p in sorted(SKILL.rglob('*')):
        if not p.is_file() or '__pycache__' in p.parts or p.suffix == '.pyc':
            continue
        if p.is_symlink() or not p.resolve().is_relative_to(SKILL.resolve()):
            raise ValueError(f'External resource: {p}')
        if p.suffix not in ALLOWED and p.name != 'LICENSE':
            raise ValueError(f'Unexpected distribution file: {p}')
        body = p.read_text(encoding='utf-8')
        if re.search(r'(?<![A-Za-z0-9:/])/(?:Users|home)/|sk-[A-Za-z0-9]{20,}|BEGIN .*PRIVATE KEY', body):
            raise ValueError(f'Private path or credential candidate: {p}')
        files.append(p)
    out = ROOT / 'releases'
    out.mkdir(exist_ok=True)
    archive = out / f'tennisprism-{version}.zip'
    manifest = out / f'tennisprism-{version}.manifest.json'
    if archive.exists() or manifest.exists():
        raise FileExistsError('Release already exists; use a new version, never overwrite a release')
    with zipfile.ZipFile(archive, 'x', compression=zipfile.ZIP_DEFLATED) as z:
        for p in files:
            z.write(p, (Path('tennisprism') / p.relative_to(SKILL)).as_posix())
    with zipfile.ZipFile(archive) as z:
        if z.testzip() is not None:
            raise ValueError('Archive integrity failure')
    result = {'name':'tennisprism','version':version,'files':[
        {'path':p.relative_to(SKILL).as_posix(),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
        for p in files], 'archive_sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),
        'size_bytes':archive.stat().st_size,'private_media_included':False}
    with manifest.open('x', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(json.dumps({'archive':str(archive),'manifest':str(manifest),'file_count':len(files),'size_bytes':result['size_bytes']},ensure_ascii=False))

if __name__ == '__main__':
    main()
