"""Package only explicitly approved scenic reference photos, never research pages.

Crop boxes are manually reviewed against the supplied photos. Originals are
untouched. Attribution/rights remain pending; no inpainting or watermark removal.
"""
import argparse,hashlib,json,sqlite3,shutil
from pathlib import Path
from PIL import Image
ROOT=Path(__file__).resolve().parents[1]
# Original image pixel coordinates; excludes site chrome and ordinary guide titles.
CROPS={1073:(5,10,458,630),1074:(0,235,644,597),1075:(0,390,480,709),
       1076:(145,445,675,675),1077:(68,0,464,670),1078:(8,10,524,670),
       1079:(52,50,482,670),1080:(52,270,482,670),1081:(52,50,482,330),
       1082:(52,50,482,670),1083:(52,50,482,670),1084:(52,50,482,670)}
def main():
    p=argparse.ArgumentParser();p.add_argument('--source-db',type=Path,required=True);args=p.parse_args()
    public=ROOT/'bundled_data';photos=public/'reference-photos';photos.mkdir(exist_ok=True)
    source=sqlite3.connect(args.source_db.resolve().as_uri()+'?mode=ro',uri=True);source.row_factory=sqlite3.Row
    rows=source.execute("SELECT m.*,s.name,c.name city FROM spot_media m JOIN spots s ON s.id=m.spot_id JOIN cities c ON c.id=s.city_id WHERE m.provider='xhs_screenshot' AND m.rights_status='pending' AND m.id=(SELECT max(x.id) FROM spot_media x WHERE x.spot_id=m.spot_id AND x.provider='xhs_screenshot' AND x.rights_status='pending') ORDER BY m.id").fetchall()
    assert len(rows)==18,'Review newly added photos before extending release scope'
    records=[]
    conn=sqlite3.connect(public/'travel.db');conn.execute('PRAGMA foreign_keys=ON')
    with conn:
        for row in rows:
            original=(args.source_db.parent/row['storage_path']).resolve()
            assert original.is_relative_to((args.source_db.parent/'private/xhs-screenshots').resolve())
            with Image.open(original) as im:
                box=CROPS.get(row['id'],(0,0,*im.size))
                assert 0<=box[0]<box[2]<=im.width and 0<=box[1]<box[3]<=im.height
                import io
                out=io.BytesIO();im.crop(box).convert('RGB').save(out,format='JPEG',quality=95)
                data=out.getvalue()
            digest=hashlib.sha256(data).hexdigest();name=digest+'.jpg';dest=photos/name
            if dest.exists():assert dest.read_bytes()==data
            else:dest.write_bytes(data)
            license_note=row['license_note']+'；用户明确要求纳入发布包；截图公开转载授权未核实，不能视为已授权。纯裁剪界面边缘，未补画景物。'
            storage='private/xhs-screenshots/release-references/'+name
            existing=conn.execute('SELECT spot_id,storage_path FROM spot_media WHERE id=?',(row['id'],)).fetchone()
            if existing:
                assert existing[0]==row['spot_id'] and existing[1].startswith('private/xhs-screenshots/release-references/'),'Media ID collision'
                conn.execute("UPDATE spot_media SET storage_path=?,license_note=? WHERE id=? AND provider='xhs_screenshot' AND rights_status='pending'",(storage,license_note,row['id']))
            else:conn.execute('INSERT INTO spot_media(id,spot_id,storage_path,origin_url,provider,license_note,rights_status,captured_at,created_at) VALUES(?,?,?,?,?,?,?,?,?)',
                (row['id'],row['spot_id'],storage,row['origin_url'],'xhs_screenshot',license_note,'pending',row['captured_at'],row['created_at']))
            records.append({'media_id':row['id'],'spot_id':row['spot_id'],'city':row['city'],'name':row['name'],
                'file':'reference-photos/'+name,'sha256':digest,'source_sha256':hashlib.sha256(original.read_bytes()).hexdigest(),
                'crop_box':box,'source_url':row['origin_url'],'attribution':license_note,'rights_status':'pending',
                'public_redistribution_authorization':'not_verified','included_by':'explicit_user_request',
                'modifications':'crop_only_no_inpainting','display_scope':'loopback_only'})
        assert not conn.execute('PRAGMA foreign_key_check').fetchall()
    total_media=conn.execute('SELECT count(*) FROM spot_media').fetchone()[0]
    conn.execute("UPDATE release_metadata SET version='1.1.1'");conn.commit();conn.execute('VACUUM')
    assert conn.execute('PRAGMA integrity_check').fetchone()[0]=='ok';conn.close();source.close()
    (public/'reference-photos.json').write_text(json.dumps(records,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    manifest=json.loads((public/'manifest.json').read_text(encoding='utf-8'));manifest['version']='1.1.1'
    manifest['counts']['reference_photos']=len(records);manifest['counts']['spot_media']=total_media
    manifest['privacy']='No credentials, cookies, personal lists, itineraries, raw research pages, login QR or comment screenshots. 18 scenic reference photos explicitly requested by user retain pending rights and attribution.'
    manifest['files']={str(f.relative_to(public)).replace('\\','/'):hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(public.rglob('*')) if f.is_file() and f.name!='manifest.json'}
    (public/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'reference_photos':len(records),'cropped':len(CROPS),'rights':'pending','originals_changed':False},ensure_ascii=False))
if __name__=='__main__':main()
