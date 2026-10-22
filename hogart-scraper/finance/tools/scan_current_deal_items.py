import sys,json
sys.path[:0]=['/home/kocher.av/.report-venv/lib/python3.14/site-packages','/home/kocher.av/hogart-scraper/finance']
from post_confirmed import *
a=MegaplanAPI();D=ROOT/'evidence/continuation_oct6';result=wait_budget(a._call,'GET','/deal',params={'limit':100,'fields':['positions','description'],'pageAfter':{'contentType':'Deal','id':'834'}});atomic(D/'current_deals.json',result);assert not result['meta']['pagination']['hasMoreNext'];print(len(result['data']))
terms=['HSU-09HQJ103','AB105S2LR1FA','AS25HQJ2HRA','1U50S2SJ3FA','HSU-07HQJ103','4U75S2SR5FA','550 Humi','JLV135']
for t in terms:
 out=[]
 for d in result['data']:
  if d['id'] in {'871','876'}:continue
  rows=[(x.get('name'),x.get('quantity')) for x in d.get('positions',[]) if t.casefold() in str(x.get('name','')).casefold()]
  if rows:out.append((d['id'],d.get('description'),rows))
 print(t,out,flush=True)
