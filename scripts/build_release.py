"""Non-overwriting Windows portable release builder using a tested embed runtime."""
import argparse, hashlib, json, os, shutil, subprocess, zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
VERSION='1.2.0'
def build(runtime, destination=None):
    build=(destination or ROOT/'dist')/f'travel-planner-{VERSION}-windows-x64'
    if build.exists(): raise RuntimeError('Build already exists; nothing deleted')
    manifest=json.loads((ROOT/'bundled_data/manifest.json').read_text(encoding='utf-8'))
    for name,digest in manifest['files'].items():
        assert hashlib.sha256((ROOT/'bundled_data'/name).read_bytes()).hexdigest()==digest,name
    build.mkdir(parents=True)
    ignore=shutil.ignore_patterns('__pycache__','*.pyc','tests','.env','*.log')
    for name in ('backend','frontend','bundled_data'): shutil.copytree(ROOT/name,build/name,ignore=ignore)
    shutil.copytree(runtime,build/'runtime',ignore=ignore)
    for pth in (build/'runtime').glob('python*._pth'): pth.write_text('python313.zip\n.\nLib\\site-packages\n..\nimport site\n',encoding='utf-8')
    subprocess.run([str(build/'runtime/python.exe'),'-B','-c','import fastapi,uvicorn,requests,reportlab,PIL,sqlite3;print("Runtime OK")'],cwd=build,check=True)
    shutil.copy2(ROOT/'scripts/launch_portable.py',build/'launch.py')
    for name in ('.env.example','README.md','THIRD_PARTY_NOTICES.md','CHANGELOG.md'): shutil.copy2(ROOT/name,build/name)
    revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    metadata={'version':VERSION,'revision':revision,'files':{str(p.relative_to(build)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest() for folder in ('backend','frontend') for p in sorted((build/folder).rglob('*')) if p.is_file()}}
    (build/'release.json').write_text(json.dumps(metadata,indent=2),encoding='utf-8')
    for name,args in [('start.bat',''),('start-lan.bat',' --lan')]:
        (build/name).write_text('@echo off\r\nchcp 65001 >nul\r\ncd /d "%~dp0"\r\nruntime\\python.exe launch.py'+args+'\r\npause\r\n',encoding='utf-8')
    archive=build.parent/(build.name+'.zip')
    with zipfile.ZipFile(archive,'x',zipfile.ZIP_DEFLATED,compresslevel=6) as out:
        for f in sorted(build.rglob('*')):
            if f.is_file() and '__pycache__' not in f.parts and f.suffix!='.pyc': out.write(f,f.relative_to(build.parent))
    archive.with_suffix('.zip.sha256').write_text(hashlib.sha256(archive.read_bytes()).hexdigest()+'  '+archive.name+'\n',encoding='ascii')
    print(archive,archive.stat().st_size)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--runtime',type=Path,required=True);p.add_argument('--destination',type=Path)
    args=p.parse_args();build(args.runtime.resolve(),args.destination)
