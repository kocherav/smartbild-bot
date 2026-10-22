import sys
sys.path[:0]=['/home/kocher.av/.report-venv/lib/python3.14/site-packages','/home/kocher.av/hogart-scraper/finance']
from post_confirmed import *
a=MegaplanAPI();D=ROOT/'evidence/filters1280';D.mkdir(exist_ok=True)
for ident in ['854','856']:
 x=wait_budget(a._call,'GET','/deal/'+ident);atomic(D/('deal_'+ident+'.json'),x);print(ident,[(p.get('id'),p.get('name'),p.get('quantity')) for p in x['data'].get('positions',[])],flush=True)
