import sys,json,os
from pathlib import Path
sys.path.insert(0,'/home/kocher.av/megaplan-crm')
from megaplan_api import MegaplanAPI
from contract_invoice import v1_auth,v1_call
from megaplan_finance import megaplan_operations
r=Path('/home/kocher.av/hogart-scraper/finance/evidence/posting');r.mkdir(exist_ok=True)
a=MegaplanAPI();auth=v1_auth(a);items=megaplan_operations(a,auth);p=r/'remote_operations.json';p.write_text(json.dumps(items,ensure_ascii=False,indent=2));os.chown(p,1001,27);print('operations',len(items),flush=True)
for name,path,form in [('types','/BumsFinApiV01/OperationType/list.api',{}),('accounts','/BumsFinApiV01/Account/list.api',{}),('sample','/BumsFinApiV01/Operation/card.api',{'Id':'2954'})]:
 try:
  d=v1_call(a,path,form,auth);p=r/(name+'.json');p.write_text(json.dumps(d,ensure_ascii=False,indent=2));os.chown(p,1001,27);print(name,str(d)[:700],flush=True)
 except Exception as e:print(name,type(e).__name__,flush=True)
