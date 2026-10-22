import sys,json
sys.path[:0]=['/home/kocher.av/.report-venv/lib/python3.14/site-packages','/home/kocher.av/hogart-scraper/finance']
from post_confirmed import *
a=MegaplanAPI();D=ROOT/'evidence/deep_review'
for term in ['772940222271','Вовченко','Копирка']:
 r=wait_budget(a._call,'GET','/contractorCompany/search',params={'q':term});atomic(D/('search_'+term+'.json'),r);print(term,[(x.get('id'),x.get('name')) for x in r['data']],flush=True)
atomic(D/'deal_846.json',wait_budget(a._call,'GET','/deal/846'))
