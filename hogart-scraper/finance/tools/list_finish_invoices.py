import sys
sys.path[:0]=['/home/kocher.av/.report-venv/lib/python3.14/site-packages','/home/kocher.av/hogart-scraper/finance']
from post_confirmed import *
a=MegaplanAPI();out=[];params={'limit':100,'fields':['payer','recipient','deal','rows','financeOperations','comment','conditions']};D=ROOT/'evidence/finish_all'
while True:
 r=wait_budget(a._call,'GET','/invoice',params=params);data=r['data'];assert not ({x['id'] for x in out}&{x['id'] for x in data});out.extend(data);atomic(D/'all_invoices.json',out);print('invoices',len(out),flush=True)
 if len(data)<100:break
 params['pageAfter']={'contentType':'Invoice','id':data[-1]['id']}
