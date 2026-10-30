"""Read-only ZIP/credential audit, then create a fresh, non-overwriting QA copy.

Local secret values are compared only in memory; reports contain counts/paths,
never matching credential bytes. No archive-supplied code is executed.
"""
import argparse
import hashlib
import io
import json
import os
import re
import sqlite3
import subprocess
import zipfile
from pathlib import Path, PurePosixPath

ROOT=Path(__file__).resolve().parents[1]
PATTERN=re.compile(rb'(?:sk-[A-Za-z0-9_-]{28,}|gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{50,}|-----BEGIN [A-Z ]*PRIVATE KEY-----)')


def known_credentials():
    values=set()
    roots=[ROOT,Path('D:/Harness工作区/travel-planner'),
           Path('D:/Harness工作区/travel-planner/dist/旅行智规-免安装版')]
    for root in roots:
        path=root/'.env'
        if path.is_file():
            for line in path.read_text(encoding='utf-8-sig').splitlines():
                if line.strip().startswith('#') or '=' not in line: continue
                name,value=line.split('=',1);value=value.strip().strip('\"\'')
                if any(x in name.upper() for x in ('KEY','TOKEN','SECRET')) and len(value)>=16:
                    values.add(value.encode())
        path=root/'data/private/ai_settings.json'
        if path.is_file():
            value=json.loads(path.read_text(encoding='utf-8-sig')).get('api_key','')
            if isinstance(value,str) and len(value)>=16: values.add(value.encode())
    for name,value in os.environ.items():
        if any(x in name.upper() for x in ('API_KEY','AMAP_KEY')) and len(value)>=16: values.add(value.encode())
    return values


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive',type=Path)
    parser.add_argument('destination',type=Path)
    args=parser.parse_args()
    archive_path=args.archive.resolve();dest=args.destination.resolve()
    assert not dest.exists(),'Never overwrite an existing extraction'
    assert dest.is_relative_to(ROOT/'output'),'QA destination must be within project/output'
    digest=hashlib.sha256(archive_path.read_bytes()).hexdigest()
    assert archive_path.with_suffix('.zip.sha256').read_text().split()[0]==digest
    secrets=known_credentials();hits=[];scanned=0
    def scan(data,label,depth=0):
        nonlocal scanned
        scanned+=1
        if any(value in data for value in secrets): hits.append({'path':label,'reason':'known credential'})
        if PATTERN.search(data): hits.append({'path':label,'reason':'credential pattern'})
        if depth<2 and data.startswith(b'PK\x03\x04'):
            with zipfile.ZipFile(io.BytesIO(data)) as nested:
                for entry in nested.infolist():
                    if not entry.is_dir(): scan(nested.read(entry),label+'!'+entry.filename,depth+1)
    with zipfile.ZipFile(archive_path) as archive:
        assert archive.testzip() is None
        names=archive.namelist()
        assert len(names)==len({n.lower() for n in names})
        roots={PurePosixPath(n).parts[0] for n in names}
        assert len(roots)==1
        prefix=next(iter(roots))+'/'
        metadata=json.loads(archive.read(prefix+'release.json'))
        version=metadata['version'];assert re.fullmatch(r'\d+\.\d+\.\d+',version)
        assert prefix==f'travel-planner-{version}-windows-x64/'
        revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
        assert metadata['revision']==revision
        for entry in archive.infolist():
            name=entry.filename;path=PurePosixPath(name)
            assert name.startswith(prefix) and not path.is_absolute()
            assert '..' not in path.parts and '\\' not in name and ':' not in name
            relative=name[len(prefix):]
            assert not relative.startswith(('data/','output/','dist/','.git/')),name
            assert not any(p in {'screenshots','xhs-screenshots','reference-images'} for p in path.parts),name
            assert path.name not in {'.env','.env.production','ai_settings.json','xhs_cookies.json','login-required.jpg','original-upload.zip'},name
            if not entry.is_dir(): scan(archive.read(entry),name)
        for name,expected in metadata['files'].items():
            data=archive.read(prefix+name)
            assert hashlib.sha256(data).hexdigest()==expected,name
            assert data==(ROOT/name).read_bytes(),name
        manifest=json.loads(archive.read(prefix+'bundled_data/manifest.json'))
        for name,expected in manifest['files'].items():
            assert hashlib.sha256(archive.read(prefix+'bundled_data/'+name)).hexdigest()==expected,name
        examples=archive.read(prefix+'.env.example').decode()
        assert all(not l.split('=',1)[1].strip() for l in examples.splitlines() if '=' in l and not l.strip().startswith('#'))
        report={'archive':archive_path.name,'bytes':archive_path.stat().st_size,'sha256':digest,
                'version':version,'revision':revision,'files_scanned_including_nested':scanned,
                'known_credentials_checked':len(secrets),'findings':hits,
                'code_files_verified':len(metadata['files']),'bundled_files_verified':len(manifest['files']),
                'counts':manifest['counts']}
        assert not hits,'Credential audit findings; all values deliberately withheld'
        dest.mkdir(parents=True)
        archive.extractall(dest)
    extracted=dest/prefix
    with sqlite3.connect((extracted/'bundled_data/travel.db').as_uri()+'?mode=ro',uri=True) as conn:
        assert conn.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert not conn.execute('PRAGMA foreign_key_check').fetchall()
        for table in ('cities','spots','curated_reviews','spot_media','cart_items','plans','notes'):
            assert conn.execute(f'SELECT count(*) FROM {table}').fetchone()[0]==manifest['counts'][table],table
        for table in ('cart_items','plans','notes','spot_summaries'):
            assert conn.execute(f'SELECT count(*) FROM {table}').fetchone()[0]==0,table
        public_count=reference_count=0
        for path,rights,provider in conn.execute('SELECT storage_path,rights_status,provider FROM spot_media'):
            if rights=='verified':
                assert path.startswith('/bundled-images/')
                file=extracted/'bundled_data/images'/path.removeprefix('/bundled-images/')
                assert file.is_file();public_count+=1
            else:
                assert rights=='pending' and provider in ('xhs_screenshot','web_photo')
                folder='xhs-screenshots' if provider=='xhs_screenshot' else 'web-photos'
                assert re.fullmatch(r'private/'+folder+r'/release-references/[a-f0-9]{64}\.(jpg|jpeg|png|webp)',path),path
                file=extracted/'bundled_data/reference-photos'/Path(path).name
                assert file.is_file()
                assert file.stem==hashlib.sha256(file.read_bytes()).hexdigest()
                reference_count+=1
        report.update(verified_public_media_links=public_count,pending_reference_links=reference_count)
        # JSON and SQLite must not retain development machine paths or access tokens.
        for (payload,) in conn.execute('SELECT payload_json FROM curated_reviews'):
            assert not re.search(r'xsec_token=|[CD]:[\\/](?:Users|Harness)',payload,re.I)
    report_path=ROOT/'output'/f'release-audit-v{version}.json'
    report_path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False))
    print('Fresh extraction:',str(extracted))


if __name__=='__main__': main()
