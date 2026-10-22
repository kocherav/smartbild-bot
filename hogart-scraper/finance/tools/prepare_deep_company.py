import sys,json
sys.path[:0]=['/home/kocher.av/.report-venv/lib/python3.14/site-packages','/home/kocher.av/hogart-scraper/finance']
from post_confirmed import *
a=MegaplanAPI();D=ROOT/'evidence/deep_review'
for term in ['БАКСЭТ','4345115602','АМПП','7714887870']:
 r=wait_budget(a._call,'GET','/contractorCompany/search',params={'q':term});atomic(D/('search_'+term+'.json'),r);print(term,[(x.get('id'),x.get('name')) for x in r['data']],flush=True)
x=wait_budget(a._call,'GET','/payer/1002871');atomic(D/'payer_reso.json',x);assert x['data']['inn']=='7710045520'
