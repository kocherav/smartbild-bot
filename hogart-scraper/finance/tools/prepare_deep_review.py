import sys,json
sys.path[:0]=['/home/kocher.av/.report-venv/lib/python3.14/site-packages','/home/kocher.av/hogart-scraper/finance']
from post_confirmed import *
a=MegaplanAPI();D=ROOT/'evidence/deep_review'
for ident in ['857','858','861','890','894']:
 atomic(D/('deal_'+ident+'.json'),wait_budget(a._call,'GET','/deal/'+ident))
for term in ['7736192449','САНТЕХКОМПЛЕКТ','7722753969','ВсеИнструменты']:
 r=wait_budget(a._call,'GET','/contractorCompany/search',params={'q':term});atomic(D/('search_'+term+'.json'),r);print(term,[(x.get('id'),x.get('name')) for x in r['data']],flush=True)
