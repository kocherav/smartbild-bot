import sys,json,hashlib
sys.path[:0]=['/home/kocher.av/.report-venv/lib/python3.14/site-packages','/home/kocher.av/hogart-scraper/finance']
from post_confirmed import *
a=MegaplanAPI();D=ROOT/'evidence/deep_review'
r=wait_budget(a._call,'GET','/contractorHuman/1002902/payers');atomic(D/'vovchenko_payers.json',r)
print(json.dumps(r,ensure_ascii=False)[:4000])
