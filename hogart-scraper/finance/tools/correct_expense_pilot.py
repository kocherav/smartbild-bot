import sys,json
sys.path[:0]=['/home/kocher.av/.report-venv/lib/python3.14/site-packages','/home/kocher.av/hogart-scraper/finance']
from post_confirmed import *
a=MegaplanAPI();auth=wait_budget(v1_auth,a);D=ROOT/'evidence/payment_correction'
before=wait_budget(a._call,'GET','/finOperation/2966')['data'];atomic(D/'expense_v3_before.json',before)
body={'contentType':'FinOperation','id':'2966','incomeSum':{'contentType':'Money','value':0,'currency':'RUB'},'expenseSum':{'contentType':'Money','value':2561559.07,'currency':'RUB'},'controlDate':{'contentType':'DateTime','value':'2026-10-06T09:00:00+00:00'}}
res=wait_budget(a._call,'POST','/finOperation/2966',json_body=body);atomic(D/'expense_v3_save.json',res)
after=v1_call(a,'/BumsFinApiV01/Operation/card.api',{'Id':'2966'},auth)['data']['item'];atomic(D/'expense_v3_after.json',after);print(json.dumps(after,ensure_ascii=False))
