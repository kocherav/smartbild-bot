import sys,json
sys.path[:0]=['/home/kocher.av/.report-venv/lib/python3.14/site-packages','/home/kocher.av/hogart-scraper/finance']
from post_confirmed import *
a=MegaplanAPI();D=ROOT/'evidence/art_technology';D.mkdir(exist_ok=True)
atomic(D/'deal_857.json',wait_budget(a._call,'GET','/deal/857'))
for term in ['7709895139','АРТ ТЕХНОЛОГИЯ']:
 x=wait_budget(a._call,'GET','/contractorCompany/search',params={'q':term});atomic(D/('search_'+term+'.json'),x);print(term,[(i.get('id'),i.get('name')) for i in x['data']],flush=True)
