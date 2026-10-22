import sys,json,os
from pathlib import Path
sys.path.insert(0,'/home/kocher.av/hogart-scraper')
from hogart_api import HogartAPI,HogartAPIError
D=Path('/home/kocher.av/hogart-scraper/finance/evidence/deep_review');a=HogartAPI()
for o in json.loads((D/'orders.json').read_text())['items']:
 p=D/('hogart_order_'+str(o['id'])+'.json')
 if p.exists():continue
 try:
  x=a._call('GET','/order/'+str(o['id']));p.write_text(json.dumps(x,ensure_ascii=False,indent=2));os.chown(p,1001,27);print(o['id'],list(x)[:20],flush=True)
 except HogartAPIError as e:print(o['id'],'HTTP error',flush=True)
