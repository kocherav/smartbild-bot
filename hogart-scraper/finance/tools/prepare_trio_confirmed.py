import sys
sys.path[:0]=['/home/kocher.av/.report-venv/lib/python3.14/site-packages','/home/kocher.av/hogart-scraper/finance']
from post_confirmed import *
a=MegaplanAPI()
for did in ['862','867']:
 atomic(ROOT/'evidence/trio_confirmed_oct6'/('deal_'+did+'.json'),wait_budget(a._call,'GET','/deal/'+did))
 print(did,flush=True)
