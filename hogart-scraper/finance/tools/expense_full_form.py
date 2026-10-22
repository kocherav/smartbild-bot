import sys,json
sys.path[:0]=['/home/kocher.av/.report-venv/lib/python3.14/site-packages','/home/kocher.av/hogart-scraper/finance']
from post_confirmed import *
a=MegaplanAPI();auth=wait_budget(v1_auth,a);D=ROOT/'evidence/payment_correction'
p=next(x for x in json.loads(JOURNAL.read_text())['operations'].values() if x['operation_id']=='2966');p['contractor_id']='1000511';form=cash_form(p,'2026-10-06');form['Id']='2966'
atomic(D/'expense_full_form_result.json',v1_call(a,'/BumsFinApiV01/Operation/save.api',form,auth))
x=v1_call(a,'/BumsFinApiV01/Operation/card.api',{'Id':'2966'},auth)['data']['item'];atomic(D/'expense_full_form_after.json',x);print(x['Sum'],x['SecondarySum'],x['Status'])
