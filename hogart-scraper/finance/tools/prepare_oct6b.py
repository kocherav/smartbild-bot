import sys,json
sys.path[:0]=['/home/kocher.av/.report-venv/lib/python3.14/site-packages','/home/kocher.av/hogart-scraper/finance']
from post_confirmed import *
a=MegaplanAPI();D=ROOT/'evidence/continuation_oct6b'
for did in ['851','858']:
 atomic(D/('deal_'+did+'.json'),wait_budget(a._call,'GET','/deal/'+did))
 print('deal',did,flush=True)
r=wait_budget(a._call,'GET','/contractorCompany/search',params={'q':'ОЗОН'});atomic(D/'ozon_search.json',r)
for x in r['data']:print(x['id'],x.get('name'),x.get('description','')[:300])
