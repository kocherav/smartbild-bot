import sys,json
from pathlib import Path
sys.path[:0]=['/home/kocher.av/.report-venv/lib/python3.14/site-packages','/home/kocher.av/hogart-scraper/finance']
from post_confirmed import *
a=MegaplanAPI();auth=wait_budget(v1_auth,a);D=ROOT/'evidence/payment_correction'
def save(n,x):atomic(D/(n+'.json'),x)
items=wait_budget(megaplan_operations,a,auth);save('all_before',items)
j=json.loads(JOURNAL.read_text())['operations'];ids={x['operation_id'] for x in j.values()}
for o in items:
 if str(o['Id']) in ids:print(json.dumps({k:o.get(k) for k in ['Id','Sum','SecondarySum','Status','OperationType','Contractor']},ensure_ascii=False))
for n,path,form in [('invoice826','/BumsInvoiceApiV01/Invoice/card.api',{'Id':826}),('invoice_list','/BumsInvoiceApiV01/Invoice/list.api',{'Limit':100,'Offset':0})]:save(n,v1_call(a,path,form,auth))
for n,path in [('op2988','/finOperation/2988'),('invoice826_v3','/invoice/826')]:
 try:save(n,wait_budget(a._call,'GET',path))
 except Exception as e:print(n,type(e).__name__,str(e)[:150])
