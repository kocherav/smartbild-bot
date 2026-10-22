import sys,json,os
from pathlib import Path
sys.path.insert(0,'/home/kocher.av/hogart-scraper')
from hogart_api import HogartAPI,HogartAPIError
D=Path('/home/kocher.av/hogart-scraper/finance/evidence/deep_review');a=HogartAPI()
for name,path,params in [('order_expand','/order/212386',{'expand':'orderDocuments,orderItems,documents,items'}),('order_documents','/order/212386/documents',None),('documents','/document',{'filters[orderId]':212386})]:
 try:
  x=a._call('GET',path,params=params);p=D/(name+'.json');p.write_text(json.dumps(x,ensure_ascii=False,indent=2));os.chown(p,1001,27);print(name,'keys',list(x) if isinstance(x,dict) else len(x),flush=True)
 except HogartAPIError as e:print(name,'HTTP error',flush=True)
