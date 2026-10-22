import sys,json
from pathlib import Path
sys.path.insert(0,'/home/kocher.av/hogart-scraper')
from hogart_api import HogartAPI,HogartAPIError
D=Path('/home/kocher.av/hogart-scraper/finance/evidence/deep_review');a=HogartAPI()
for name,path in [('edi_orders','/api/edi/orders'),('orders','/order')]:
 try:
  x=a._call('GET',path);(D/(name+'.json')).write_text(json.dumps(x,ensure_ascii=False,indent=2));print(name,'ok',str(type(x)),list(x)[:12] if isinstance(x,dict) else len(x),flush=True)
 except HogartAPIError as e:print(name,'HTTP error',e.status if hasattr(e,'status') else type(e).__name__,flush=True)
