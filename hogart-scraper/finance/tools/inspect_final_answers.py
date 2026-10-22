import sys,json
sys.path[:0]=['/home/kocher.av/.report-venv/lib/python3.14/site-packages','/home/kocher.av/hogart-scraper/finance']
from post_confirmed import *
a=MegaplanAPI();D=ROOT/'evidence/final_answers_20261007'
for ident in ['851','855','869','892','861','857']:
 x=wait_budget(a._call,'GET','/deal/'+ident);atomic(D/('deal_'+ident+'.json'),x);d=x['data'];print('deal',ident,d.get('description'),[(p.get('name'),p.get('quantity')) for p in d.get('positions',[])][:15],flush=True)
allp=json.loads((ROOT/'evidence/payment_correction/all_payers.json').read_text())
for inn,term in [('9709017890','ИНТТЕХНО'),('9704254424','Яндекс Маркет')]:
 hits=[p for p in allp if p.get('inn')==inn];print('payer_matches',inn,[(p['id'],p.get('contractor')) for p in hits],flush=True);atomic(D/('payer_matches_'+inn+'.json'),hits)
 x=wait_budget(a._call,'GET','/contractorCompany/search',params={'q':term});atomic(D/('search_'+inn+'.json'),x);print('search',inn,[(p.get('id'),p.get('name')) for p in x['data']],flush=True)
