import sys,json
sys.path[:0]=['/home/kocher.av/.report-venv/lib/python3.14/site-packages','/home/kocher.av/hogart-scraper/finance']
from post_confirmed import *
a=MegaplanAPI();D=ROOT/'evidence/finish_all'
for name in ['МАРКЕР','СТРОЙСПЕЦПРОЕКТ','МАНГО','ВК Цифровые','ТАЙМВЭБ']:
 r=wait_budget(a._call,'GET','/contractorCompany/search',params={'q':name});atomic(D/('search_'+name+'.json'),r);print(name,[(x.get('id'),x.get('name')) for x in r['data']],flush=True)
