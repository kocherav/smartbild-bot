import sys
sys.path[:0]=['/home/kocher.av/.report-venv/lib/python3.14/site-packages','/home/kocher.av/hogart-scraper/finance']
from post_confirmed import *
a=MegaplanAPI();D=ROOT/'evidence/continuation_oct6c'
atomic(D/'deal_861.json',wait_budget(a._call,'GET','/deal/861'))
for term in ['МИГ','7719228261']:
 r=wait_budget(a._call,'GET','/contractorCompany/search',params={'q':term});atomic(D/('supplier_search_'+term+'.json'),r)
 print(term,[(x.get('id'),x.get('name')) for x in r['data']],flush=True)
