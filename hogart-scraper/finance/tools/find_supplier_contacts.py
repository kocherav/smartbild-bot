import sys,json
sys.path[:0]=['/home/kocher.av/.report-venv/lib/python3.14/site-packages','/home/kocher.av/hogart-scraper/finance']
from post_confirmed import *
a=MegaplanAPI();D=ROOT/'evidence/payment_correction'
parts=list(json.loads(JOURNAL.read_text())['operations'].values());inns=sorted({p['counterparty_inn'] for p in parts if p['kind']=='expense'})
for inn in inns:
 dest=D/('supplier_'+inn+'.json')
 if dest.exists():continue
 data=wait_budget(a._call,'GET','/contractorCompany/search',params={'q':inn});atomic(dest,data)
 print(inn,[(x.get('id'),x.get('name'),x.get('inn')) for x in data.get('data',[])],flush=True)
