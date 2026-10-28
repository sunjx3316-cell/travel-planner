"""Exercise an extracted portable release, with no developer dependencies."""
import argparse, hashlib, json, os, socket, sqlite3, subprocess, time, urllib.request, urllib.error
from pathlib import Path
def smoke(root):
    manifest=json.loads((root/'bundled_data/manifest.json').read_text(encoding='utf-8'))
    for name,digest in manifest['files'].items(): assert hashlib.sha256((root/'bundled_data'/name).read_bytes()).hexdigest()==digest,name
    with socket.socket() as s: s.bind(('127.0.0.1',0)); port=s.getsockname()[1]
    env={k:v for k,v in os.environ.items() if not any(x in k.upper() for x in ('API_KEY','AMAP','BAIDU','PYTHONPATH','TRAVEL_DB','COOKIE'))}
    env.update(DEEPSEEK_API_KEY='',AMAP_KEY='',PYTHONDONTWRITEBYTECODE='1')
    with (root/'smoke.log').open('wb') as log:
        proc=subprocess.Popen([str(root/'runtime/python.exe'),'-m','uvicorn','backend.app.main:app','--host','127.0.0.1','--port',str(port)],cwd=root,env=env,stdout=log,stderr=log)
        try:
            base=f'http://127.0.0.1:{port}'
            def get(path): return urllib.request.urlopen(base+path,timeout=10).read()
            for _ in range(80):
                if proc.poll() is not None: raise RuntimeError('Server exited: '+(root/'smoke.log').read_text(errors='replace')[-1000:])
                try: status=json.loads(get('/api/status'));break
                except OSError: time.sleep(.25)
            else: raise RuntimeError('Startup timeout')
            assert status['version']=='1.0.0' and not status['llm_available']
            assert b'data-action="rail"' in get('/')
            conn=sqlite3.connect(root/'data/travel.db')
            assert conn.execute('SELECT COUNT(*) FROM spots').fetchone()[0]==manifest['counts']['spots']
            assert conn.execute('SELECT COUNT(*) FROM cart_items').fetchone()[0]==0
            sid,path=conn.execute('SELECT spot_id,storage_path FROM spot_media LIMIT 1').fetchone()
            assert len(get(path))>100
            detail=json.loads(get(f'/api/spots/{sid}'))
            assert detail['curated_review'] and detail['image_assets']
            assert b'<html' in get('/rail/').lower()
            for path in ('/media/travel.db','/media/xhs_cookies.json','/bundled_data/travel.db'):
                try: get(path);raise AssertionError('Private data served: '+path)
                except urllib.error.HTTPError as e: assert e.code==404
            plan={'name':'天津到桂林 · 日历与铁路联动','daily':[{'items':[{'spot':'桂林博物馆','time':'上午'},{'spot':'山水漫步','time':'下午'}]} for _ in range(3)],'rail_journeys':[{'date':'2026-10-29','from':'天津','to':'桂林','snapshot':'20261020','risk':'换乘需核实','legs':[{'train':'G123','from':'天津西','to':'桂林北','departure':1380,'arrival':1920}]}]}
            req=urllib.request.Request(base+'/api/plans/export-pdf',data=json.dumps(plan).encode(),headers={'Content-Type':'application/json'})
            pdf=urllib.request.urlopen(req,timeout=30).read();assert pdf.startswith(b'%PDF')
            (root/'smoke-itinerary.pdf').write_bytes(pdf)
            print(json.dumps({'status':status,'counts':manifest['counts'],'pdf_bytes':len(pdf),'port':port},ensure_ascii=False))
        finally:
            proc.terminate();proc.wait(timeout=15)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);smoke(p.parse_args().root.resolve())
