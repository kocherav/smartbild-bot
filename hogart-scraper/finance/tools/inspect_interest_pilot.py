import sys
sys.path[:0]=['/home/kocher.av/.report-venv/lib/python3.14/site-packages','/home/kocher.av/hogart-scraper/finance']
from post_confirmed import *
a=MegaplanAPI();auth=wait_budget(v1_auth,a)
for op in ['3000','3051']:
 x=v1_call(a,'/BumsFinApiV01/Operation/card.api',{'Id':op},auth);atomic(ROOT/'evidence/remaining_oct6'/('card_'+op+'.json'),x)
 y=wait_budget(a._call,'GET','/finOperation/'+op);atomic(ROOT/'evidence/remaining_oct6'/('v3_'+op+'.json'),y)
 print(op,[(k,v) for k,v in x['data']['item'].items() if k in ['Kind','OperationType','Sum','SecondarySum','Name','Type']],flush=True)
 print({k:v for k,v in y['data'].items() if k in ['incomeSum','expenseSum','type','kind','description','finOperationType']},flush=True)
