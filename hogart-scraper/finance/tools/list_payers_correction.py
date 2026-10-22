import sys,json
sys.path[:0]=['/home/kocher.av/.report-venv/lib/python3.14/site-packages','/home/kocher.av/hogart-scraper/finance']
from post_confirmed import *
a=MegaplanAPI();D=ROOT/'evidence/payment_correction';allitems=[];last=None
for page in range(50):
 params={'limit':100}
 if last:params['pageAfter']={'contentType':'Payer','id':last}
 d=wait_budget(a._call,'GET','/payer',params=params);atomic(D/('payers_page_'+str(page)+'.json'),d);items=d['data'];allitems+=items;print(page,len(items),d.get('meta',{}).get('pagination'),flush=True)
 if not items or not d.get('meta',{}).get('pagination',{}).get('hasMoreNext',len(items)==100):break
 if items[-1]['id']==last:raise ValueError('No paging progress')
 last=items[-1]['id']
atomic(D/'all_payers.json',allitems)
