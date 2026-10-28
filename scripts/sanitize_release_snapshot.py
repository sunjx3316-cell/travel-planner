"""Remove temporary platform access signatures from public review links."""
import hashlib,json,re,sqlite3
from pathlib import Path
root=Path(__file__).resolve().parents[1]/'bundled_data'
conn=sqlite3.connect(root/'travel.db');changed=0
for key,payload in conn.execute('SELECT catalog_key,payload_json FROM curated_reviews').fetchall():
    clean=re.sub(r'([?&])xsec_token=[^&#"\\\s]*',r'\1',payload)
    if clean!=payload:
        json.loads(clean)
        conn.execute('UPDATE curated_reviews SET payload_json=? WHERE catalog_key=?',(clean,key));changed+=1
conn.commit();conn.execute('VACUUM');conn.close()
manifest=json.loads((root/'manifest.json').read_text(encoding='utf-8'))
manifest['files']={str(p.relative_to(root)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(root.rglob('*')) if p.is_file() and p.name!='manifest.json'}
manifest['privacy']+=' Temporary xsec_token URL signatures removed.'
(root/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
print('Sanitized records:',changed)
