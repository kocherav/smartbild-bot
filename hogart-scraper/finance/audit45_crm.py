import json,sys,os
from pathlib import Path
sys.path.insert(0,'/home/kocher.av/megaplan-crm');from megaplan_api import MegaplanAPI
root=Path('/home/kocher.av/hogart-scraper/finance/evidence');cache=json.loads(Path('/home/kocher.av/megaplan-crm/deal_browser_cache.json').read_text());api=MegaplanAPI()
selected=[d for d in cache if d.get('timeUpdated',{}).get('value','')>='2026-04-01' or d.get('timeCreated',{}).get('value','')>='2026-04-01'];print('deals',len(selected),flush=True)
for d in selected:
 ident=d['id'];dest=root/f'files_{ident}.json'
 if dest.exists():continue
 try:
  data=api._call('GET',f'/deal/{ident}/allFiles',params={'limit':100});dest.write_text(json.dumps(data,ensure_ascii=False));os.chown(dest,1001,27);os.chmod(dest,0o600);print(ident,len(data.get('data',[])),flush=True)
 except Exception as exc:print(ident,type(exc).__name__,flush=True);break
