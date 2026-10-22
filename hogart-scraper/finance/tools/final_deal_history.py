import sys,json
sys.path[:0]=['/home/kocher.av/.report-venv/lib/python3.14/site-packages','/home/kocher.av/hogart-scraper/finance']
from post_confirmed import *
a=MegaplanAPI();D=ROOT/'evidence/final_answers_20261007'
for ident in ['855','869']:
 x=wait_budget(a._call,'GET','/deal/'+ident+'/history',params={'limit':100});atomic(D/('history_'+ident+'.json'),x);print('history',ident,len(x['data']),x.get('meta',{}).get('pagination'),flush=True)
 for t in x['data']:
  s=json.dumps(t,ensure_ascii=False)
  if 'AS20' in s or '42965' in s or '44245' in s:print(s[:3000],flush=True)
