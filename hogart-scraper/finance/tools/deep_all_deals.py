import sys,json
sys.path[:0]=['/home/kocher.av/.report-venv/lib/python3.14/site-packages','/home/kocher.av/hogart-scraper/finance']
from post_confirmed import *
a=MegaplanAPI();D=ROOT/'evidence/deep_review';out=[];after=None
for n in range(20):
 params={'limit':100,'fields':['positions','description']}
 if after:params['pageAfter']={'contentType':'Deal','id':after}
 p=D/('all_deals_page_'+str(n)+'.json')
 x=json.loads(p.read_text()) if p.exists() else wait_budget(a._call,'GET','/deal',params=params)
 atomic(p,x);out.extend(x['data']);print(n,len(x['data']),flush=True)
 if not x['meta']['pagination']['hasMoreNext']:break
 after=x['data'][-1]['id']
else:raise ValueError('pagination incomplete')
atomic(D/'all_deals.json',out);print('all',len(out),flush=True)
