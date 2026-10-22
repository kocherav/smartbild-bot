import sys,json,time
from pathlib import Path
from collections import Counter
sys.path[:0]=['/home/kocher.av/megaplan-crm','/home/kocher.av/hogart-scraper/dashboard']
from megaplan_api import MegaplanAPI
from sync import fetch
from position_types import FIELD,classify_position
from position_type_migration import invariant
p=Path(__file__).parent
api=MegaplanAPI()
a=fetch(api,'/deal','Deal',['positions','result','program','state','price'])
(p/'all-deals-after.json').write_text(json.dumps(a,ensure_ascii=False))
b=json.loads((p/'all-deals.json').read_text()); old={str(d['id']):d for d in b if str((d.get('program') or {}).get('id'))=='16' and d.get('result')=='active'}
new={str(d['id']):d for d in a}; counts=Counter(); offers={};changes=[]
for did,d in old.items():
 n=new[did]
 assert d['price']==n['price'],did
 prev={str(r['id']):r for r in d.get('positions',[])}
 assert set(prev)=={str(r['id']) for r in n.get('positions',[])},did
 for r in n.get('positions',[]):
  before=prev[str(r['id'])]
  for k in ('name','quantity','unit','price','sum','tax','discount'):
   assert before.get(k)==r.get(k),(did,r['id'],k)
  assert invariant(before['offer'])==invariant(r['offer']),(did,r['id'],'offer invariants')
  counts[classify_position(r)]+=1; offers[str(r['offer']['id'])]=r['offer']
plan=json.loads((p/'current-migration-plan.json').read_text())
for c in plan:assert offers[c['offer_id']].get(FIELD)==c['after'],c
r={'deals':len(old),'positions':sum(counts.values()),'kinds':dict(counts),'migrated_verified':len(plan),'invariants_unchanged':True}
(p/'live-verification.json').write_text(json.dumps(r,ensure_ascii=False,indent=2));print(json.dumps(r))
(p/'live-861-after.json').write_text(json.dumps(new['861'],ensure_ascii=False))
