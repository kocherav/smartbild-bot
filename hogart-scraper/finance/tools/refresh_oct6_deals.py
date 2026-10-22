import sys,json
sys.path[:0]=['/home/kocher.av/.report-venv/lib/python3.14/site-packages','/home/kocher.av/hogart-scraper/finance']
from post_confirmed import *
a=MegaplanAPI();D=ROOT/'evidence/continuation_oct6'
for did in ['858','861','862','894']:
 d=wait_budget(a._call,'GET','/deal/'+did);atomic(D/('deal_'+did+'.json'),d);print('deal',did,flush=True)
atomic(D/'turkov_search.json',wait_budget(a._call,'GET','/contractorCompany/search',params={'q':'ТУРКОВ'}))
