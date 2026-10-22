import sys
sys.path[:0]=['/home/kocher.av/.report-venv/lib/python3.14/site-packages','/home/kocher.av/hogart-scraper/finance']
from post_confirmed import *
a=MegaplanAPI();D=ROOT/'evidence/deep_review';mp=ROOT/'evidence/payment_correction/supplier_mapping.json';m=json.loads(mp.read_text())
for inn,pid,cid in [('7736192449','1000225','1000223'),('7722753969','1000784','1000756')]:
 x=wait_budget(a._call,'GET','/payer/'+pid);atomic(D/('payer_'+pid+'.json'),x);assert x['data']['inn']==inn and x['data']['contractor']['id']==cid
 m[inn]={'contractor_id':cid,'state':'existing','basis':'ИНН проверен в актуальном плательщике'+pid+'; использована существующая карточка, без дубля.'}
atomic(mp,m)
