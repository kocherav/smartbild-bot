import sys,json,re,os
from pathlib import Path
sys.path.insert(0,'/home/kocher.av/megaplan-crm')
from megaplan_api import MegaplanAPI
BASE=Path('/home/kocher.av/hogart-scraper/finance');rows=json.loads((BASE/'reports/ledger.json').read_text())
index=json.loads(Path('/home/kocher.av/megaplan-crm/bank_match_index.json').read_text())
deals=set();invoices=set()
for r in rows:
 if r['direction']!='in' or r['group']=='Между компаниями группы':continue
 for did in re.findall(r'1\.(\d+)-\d{4}/\d{4}',r['purpose']):deals.add(did)
 for ref in re.findall(r'(?i)сч(?:[её]т[уа]?)?\s*№?\s*(\d{4,8})',r['purpose']):
  for inv in index.get('invoice_numbers',{}).get(str(int(ref)),[]):invoices.add(inv['invoice_id']);deals.add(inv['deal_id'])
deals.update(['861','853','887','894'])
api=MegaplanAPI()
for kind,ids in [('deal',deals),('invoice',invoices)]:
 for ident in sorted(ids,key=int):
  dest=BASE/'evidence'/f'{kind}_{ident}.json'
  if dest.exists():continue
  try:
   obj=api._call('GET',f'/{kind}/{ident}')
   dest.write_text(json.dumps(obj,ensure_ascii=False,indent=2));os.chown(dest,1001,27);os.chmod(dest,0o600)
   print(kind,ident,'saved',flush=True)
  except Exception as exc:
   print(kind,ident,type(exc).__name__,flush=True);break
