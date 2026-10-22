import sys,json,os
from pathlib import Path
sys.path.insert(0,'/home/kocher.av/megaplan-crm')
from megaplan_api import MegaplanAPI
root=Path('/home/kocher.av/hogart-scraper/finance/evidence');api=MegaplanAPI()
for p in root.glob('deal_*.json'):
 ident=p.stem.split('_')[1];dest=root/f'files_{ident}.json'
 if dest.exists():continue
 try:
  data=api._call('GET',f'/deal/{ident}/allFiles',params={'limit':100})
  dest.write_text(json.dumps(data,ensure_ascii=False,indent=2));os.chown(dest,1001,27);os.chmod(dest,0o600)
  print(ident,len(data.get('data',[])),flush=True)
 except Exception as exc:print(type(exc).__name__,flush=True);break
