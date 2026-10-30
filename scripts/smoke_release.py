"""Exercise a FRESH extracted release, writing test state only to that extraction."""
import argparse, hashlib, json, os, re, socket, sqlite3, subprocess, time, urllib.request, urllib.error
from pathlib import Path
def smoke(root):
    assert not (root/'data').exists(), 'Use a fresh extraction, not a user installation'
    assert not (root/'.env').exists(), 'Release must not contain credentials'
    release=json.loads((root/'release.json').read_text(encoding='utf-8'))
    version=release['version']
    assert re.fullmatch(r'\d+\.\d+\.\d+',version)
    for name,digest in release['files'].items(): assert hashlib.sha256((root/name).read_bytes()).hexdigest()==digest,name
    manifest=json.loads((root/'bundled_data/manifest.json').read_text(encoding='utf-8'))
    for name,digest in manifest['files'].items(): assert hashlib.sha256((root/'bundled_data'/name).read_bytes()).hexdigest()==digest,name
    with socket.socket() as s: s.bind(('127.0.0.1',0)); port=s.getsockname()[1]
    env={k:v for k,v in os.environ.items() if not any(x in k.upper() for x in ('KEY','TOKEN','SECRET','AMAP','BAIDU','PYTHON','TRAVEL_','COOKIE'))}
    # Bulk asset QA is deterministic; production limiter defaults are tested separately.
    env.update(DEEPSEEK_API_KEY='',AMAP_KEY='',PYTHONDONTWRITEBYTECODE='1',RATE_LIMIT_ENABLED='0')
    # Run the real launcher; suppress only automatic browser opening during QA.
    bootstrap="import runpy,sys,webbrowser; webbrowser.open=lambda *a,**k: True; "+f"sys.argv=['launch.py','--port','{port}']; "+"runpy.run_path('launch.py',run_name='__main__')"
    with (root/'smoke.log').open('wb') as log:
        proc=subprocess.Popen([str(root/'runtime/python.exe'),'-B','-c',bootstrap],cwd=root,env=env,stdout=log,stderr=log)
        try:
            base=f'http://127.0.0.1:{port}'
            opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
            def get(path):
                with opener.open(base+path,timeout=10) as response: return response.read()
            def api(path,payload=None,headers=None):
                req=urllib.request.Request(base+path,data=json.dumps(payload,ensure_ascii=False).encode() if payload is not None else None,headers={'Content-Type':'application/json',**(headers or {})})
                with opener.open(req,timeout=60) as response: return json.loads(response.read())
            def rejects(path,code,payload=None,headers=None):
                try: api(path,payload,headers)
                except urllib.error.HTTPError as error: assert error.code==code,(path,error.code)
                else: raise AssertionError('Expected rejection: '+path)
            for _ in range(80):
                if proc.poll() is not None: raise RuntimeError('Server exited: '+(root/'smoke.log').read_text(errors='replace')[-1000:])
                try: status=json.loads(get('/api/status'));break
                except OSError: time.sleep(.25)
            else: raise RuntimeError('Startup timeout')
            assert status['version']==version and not status['llm_available']
            settings=api('/api/ai/settings')
            assert settings['mode']=='local' and not settings['configured'] and not settings['onboarded']
            assert settings['key_source']=='none' and settings['connection']['state']=='unconfigured'
            assert b'data-action="rail"' in get('/')
            assert ('/js/mode.js?v='+version).encode() in get('/')
            assert '本地规划'.encode() in get('/js/mode.js')
            assert 'AI 增强'.encode() in get('/js/mode.js')
            assert len(get('/css/mode.css'))>100
            assert b'rail:finalized' in get('/js/rail.js')
            assert b'publishSavedFinal(next.finals[0])' in get('/rail/comparison.js')
            assert b'onDelete:id' in get('/rail/comparison.js')
            assert '撤销删除'.encode() in get('/rail/decision-view.js')
            conn=sqlite3.connect(root/'data/travel.db')
            for table in ('cities','spots','curated_reviews','spot_media','cart_items','plans','notes'):
                assert conn.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]==manifest['counts'][table],table
            sid,path=conn.execute('SELECT spot_id,storage_path FROM spot_media LIMIT 1').fetchone()
            assert len(get(path))>100
            detail=json.loads(get(f'/api/spots/{sid}'))
            assert detail['curated_review'] and detail['image_assets']
            # Bundled screenshots remain pending, local-only references.  The
            # photo package contains only reviewed/cropped scenic image assets.
            references=conn.execute("SELECT id,spot_id,storage_path,rights_status,provider FROM spot_media WHERE rights_status='pending'").fetchall()
            reference_checks=[]
            for media_id,spot_id,storage_path,rights,provider in references:
                assert rights=='pending'
                assert provider in ('xhs_screenshot','web_photo')
                folder='xhs-screenshots' if provider=='xhs_screenshot' else 'web-photos'
                assert re.fullmatch(r'private/'+folder+r'/release-references/[a-f0-9]{64}\.(jpg|jpeg|png|webp)',storage_path)
                expected=root/'bundled_data/reference-photos'/Path(storage_path).name
                assert expected.is_file()
                endpoint=f'/api/local-reference-images/{media_id}'
                assert hashlib.sha256(get(endpoint)).hexdigest()==hashlib.sha256(expected.read_bytes()).hexdigest()
                details=api(f'/api/spots/{spot_id}')
                reference=next(a for a in details['image_assets'] if a.get('local_reference'))
                assert reference['rights_status']=='pending' and reference['storage_path']==endpoint
                assert details['curated_review']['digest']['method']=='semantic_reviewed'
                assert details['curated_review']['digest']['displayed_point_count']<=6
                rejected_headers=({'X-Forwarded-For':'127.0.0.1'},{'Origin':'https://evil.example'},{'Sec-Fetch-Site':'cross-site'},{'Host':'evil.example'}) if not reference_checks else ({'X-Forwarded-For':'127.0.0.1'},)
                for headers in rejected_headers:
                    rejects(endpoint,403,headers=headers)
                hidden=api(f'/api/spots/{spot_id}',headers={'X-Forwarded-For':'127.0.0.1'})
                assert not any(a.get('local_reference') for a in hidden['image_assets'])
                try: get('/bundled_data/reference-photos/'+expected.name)
                except urllib.error.HTTPError as e: assert e.code==404
                else: raise AssertionError('Raw pending reference publicly mounted')
                reference_checks.append({'spot_id':spot_id,'photo':200,'non_owner':403})
            if version=='1.1.1':
                assert len(references)==18
                assert conn.execute('SELECT count(*) FROM curated_reviews').fetchone()[0]==1333
            assert len(references)==manifest['counts']['reference_photos']
            if version=='1.2.0':
                assert conn.execute('SELECT count(distinct spot_id) FROM spot_media').fetchone()[0]==1034
                assert conn.execute('SELECT lng,lat FROM spots WHERE id=6287').fetchone()==(110.559542,29.343982)
            conn.close()
            assert b'<html' in get('/rail/').lower()
            for path in ('/media/travel.db','/media/xhs_cookies.json','/bundled_data/travel.db','/.env','/data/private/ai_settings.json'):
                try: get(path);raise AssertionError('Private data served: '+path)
                except urllib.error.HTTPError as e: assert e.code==404
            rejects('/api/ai/settings',403,{'mode':'local'})
            local_headers={'X-Travel-Settings':'1','Origin':base}
            rejects('/api/ai/settings',400,{'mode':'ai'},local_headers)
            chosen=api('/api/ai/settings',{'mode':'local'},local_headers)
            assert chosen['onboarded'] and not chosen['enabled']
            cities={c['name']:c['id'] for c in api('/api/cities')}
            guilin=api(f'/api/cities/{cities["桂林"]}/spots')[:4]
            nanning=api(f'/api/cities/{cities["南宁"]}/spots')[:2]
            cases=[
                ('single_city','/api/plans/citytour',{'spot_ids':[s['id'] for s in guilin],'days':3,'start_city':'桂林'}),
                ('multi_city','/api/plans/citytour',{'spot_ids':[s['id'] for s in guilin[:2]+nanning],'days':4,'start_city':'桂林','city_days':{'桂林':2,'南宁':2}}),
            ]
            loop=next(lp for lp in api('/api/loops') if lp['name']=='甘南环线')
            cases.append(('gannan_loop','/api/plans/roadtrip',{'spot_ids':[s['id'] for s in loop['spots']],'days':7,'style':'轻松','start_city':'兰州','close_loop':True}))
            results=[]
            for label,endpoint,payload in cases:
                plans=api(endpoint,payload)
                assert len(plans)==3,label
                for entry in plans:
                    candidate=entry['plan']
                    assert len(candidate['daily'])==payload['days'],label
                    assert candidate['generation']['state']=='local',label
                    if label=='gannan_loop':
                        assert all(d['driving_hours']<=5.01 and d['activity_hours']<=7.51 for d in candidate['daily'])
                        items=[it for d in candidate['daily'] for it in d['items']]+candidate['unscheduled']
                        ids=[it['spot_id'] for it in items if 'spot_id' in it]
                        assert set(ids)==set(payload['spot_ids']) and len(ids)==len(payload['spot_ids'])
                if label=='single_city': plan=plans[0]['plan']
                results.append({'case':label,'plans':len(plans),'days':payload['days']})
            plan['rail_journeys']=[{'date':'2026-10-29','from':'天津','to':'桂林','snapshot':'20261020','risk':'换乘需核实','legs':[{'train':'G123','from':'天津西','to':'桂林北','departure':1380,'arrival':1920}]}]
            req=urllib.request.Request(base+'/api/plans/export-pdf',data=json.dumps(plan).encode(),headers={'Content-Type':'application/json'})
            with opener.open(req,timeout=30) as response: pdf=response.read()
            assert pdf.startswith(b'%PDF') and len(pdf)>10000
            (root/'smoke-itinerary.pdf').write_bytes(pdf)
            final_status=api('/api/status')
            assert not final_status['llm_available'] and final_status['ai']['last_call'] is None
            print(json.dumps({'version':version,'revision':release['revision'],'counts':manifest['counts'],'cases':results,'reference_photos_checked':len(reference_checks),'all_reference_non_owner_denied':True,'ai_called':False,'pdf_bytes':len(pdf),'port':port},ensure_ascii=False))
        finally:
            proc.terminate();proc.wait(timeout=15)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);smoke(p.parse_args().root.resolve())
