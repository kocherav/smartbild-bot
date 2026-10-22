import sys
sys.path[:0]=['/home/kocher.av/.report-venv/lib/python3.14/site-packages','/home/kocher.av/hogart-scraper/finance']
from post_confirmed import *
a=MegaplanAPI();auth=wait_budget(v1_auth,a);r=v1_call(a,'/BumsFinApiV01/RealAccount/list.api',{},auth);atomic(ROOT/'evidence/finish_all/real_accounts.json',r)
print([(x.get('Id'),x.get('Name')) for x in r['data']['items']])
