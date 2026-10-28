"""Sanitized catalog snapshot. Does not touch the input database."""
import argparse, hashlib, json, shutil, sqlite3
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def prepare(source):
    target=ROOT/'bundled_data'; target.mkdir(exist_ok=True)
    db=target/'travel.db'
    if db.exists(): raise RuntimeError('Snapshot exists; not overwritten')
    with sqlite3.connect((source/'data/travel.db').as_uri()+'?mode=ro',uri=True) as src:
        with sqlite3.connect(db) as dst: src.backup(dst)
    conn=sqlite3.connect(db)
    for table in ('cart_items','plans','notes','spot_summaries'): conn.execute(f'DELETE FROM {table}')
    conn.execute("DELETE FROM spot_media WHERE rights_status != 'verified'")
    conn.execute('CREATE TABLE release_metadata(version TEXT NOT NULL)')
    conn.execute("INSERT INTO release_metadata VALUES ('1.0.0')")
    images={}
    for identifier,storage in conn.execute('SELECT id,storage_path FROM spot_media').fetchall():
        relative=storage.removeprefix('/media/').removeprefix('/').removeprefix('media/')
        path=(source/'data'/relative).resolve()
        if not path.is_relative_to((source/'data/images').resolve()) or not path.is_file(): raise RuntimeError('Missing/unsafe image: '+relative)
        dest=target/'images'/path.name
        if dest.name in images and images[dest.name]!=path: raise RuntimeError('Image basename collision')
        images[dest.name]=path; dest.parent.mkdir(exist_ok=True); shutil.copy2(path,dest)
        conn.execute('UPDATE spot_media SET storage_path=? WHERE id=?',('/bundled-images/'+dest.name,identifier))
    conn.commit(); conn.execute('VACUUM')
    assert conn.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    assert not conn.execute('PRAGMA foreign_key_check').fetchall()
    counts={t:conn.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0] for t in ('cities','spots','curated_reviews','spot_media','cart_items','plans','notes')}
    counts['review_status']=dict(conn.execute('SELECT review_status,COUNT(*) FROM curated_reviews GROUP BY review_status'))
    counts['images']=len(images); conn.close()
    manifest={'version':'1.0.0','counts':counts,'privacy':'No credentials, cookies, carts, saved plans, raw notes or demo summaries.', 'files':{str(p.relative_to(target)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(target.rglob('*')) if p.is_file()}}
    (target/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(counts,ensure_ascii=False))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);prepare(p.parse_args().source.resolve())
