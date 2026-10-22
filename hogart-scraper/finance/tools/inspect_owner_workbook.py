import sys,json
sys.path[:0]=['/home/kocher.av/.report-venv/lib/python3.14/site-packages','/home/kocher.av/hogart-scraper/finance']
from post_confirmed import *
a=MegaplanAPI();D=ROOT/'evidence/owner_workbook_20261007'
for ident in ['836','847','853','861','862','863','867','890','894']:
 x=wait_budget(a._call,'GET','/deal/'+ident);atomic(D/('deal_'+ident+'.json'),x);print('deal',ident,x['data'].get('description'),flush=True)
for term in ['Шишаев','332904300538','Андросова','Беккер','Борисик','А Торг','Шишаева']:
 for kind in ['contractorHuman','contractorCompany']:
  x=wait_budget(a._call,'GET','/'+kind+'/search',params={'q':term});atomic(D/('search_'+kind+'_'+term+'.json'),x);print(kind,term,[(r.get('id'),r.get('name')) for r in x['data']],flush=True)
