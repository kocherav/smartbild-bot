import sys,json
sys.path[:0]=['/home/kocher.av/.report-venv/lib/python3.14/site-packages','/home/kocher.av/hogart-scraper/finance']
from post_confirmed import *
a=MegaplanAPI();auth=wait_budget(v1_auth,a);D=ROOT/'evidence/payment_correction'
before=v1_call(a,'/BumsFinApiV01/Operation/card.api',{'Id':'2988'},auth)['data']['item'];atomic(D/'pilot_before.json',before)
assert cents(before['Sum']['Value'])==39012300 and before['DocumentNumber']=='2697'
form={'Id':'2988','Model[SecondarySum][Value]':'0.00','Model[SecondarySum][Currency]':'1','Model[Contractor]':'1002845','Model[Invoice]':'826','Model[ControlDate]':'2026-10-06'}
response=v1_call(a,'/BumsFinApiV01/Operation/save.api',form,auth);atomic(D/'pilot_save.json',response)
after=v1_call(a,'/BumsFinApiV01/Operation/card.api',{'Id':'2988'},auth);atomic(D/'pilot_after.json',after)
for n,path in [('pilot_v3','/finOperation/2988'),('pilot_invoice','/invoice/826')]:atomic(D/(n+'.json'),wait_budget(a._call,'GET',path))
print(json.dumps(after,ensure_ascii=False))
