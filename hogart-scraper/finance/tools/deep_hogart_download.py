import sys,json,os,urllib.request,hashlib,subprocess
from pathlib import Path
sys.path.insert(0,'/home/kocher.av/hogart-scraper')
from hogart_api import HogartAPI
D=Path('/home/kocher.av/hogart-scraper/finance/evidence/deep_review');a=HogartAPI();out=[]
for page in [1,2]:
 x=a._call('GET','/document',params={'page':page});out.extend(x['items'])
(D/'hogart_documents.json').write_text(json.dumps(out,ensure_ascii=False,indent=2));os.chown(D/'hogart_documents.json',1001,27)
for d in out:
 if not d.get('fileUrl'):continue
 p=D/('hogart_doc_'+str(d['id'])+'.pdf')
 if not p.exists():
  assert d['fileUrl'].startswith('https://admin.b2b.hogart.ru/file/download?')
  data=urllib.request.urlopen(d['fileUrl'],timeout=40).read();assert data.startswith(b'%PDF');p.write_bytes(data);os.chown(p,1001,27)
 subprocess.run(['pdftotext','-layout',str(p),str(p.with_suffix('.txt'))],check=True);os.chown(p.with_suffix('.txt'),1001,27)
 print(d['number'],d['docDate'],d['documentItemsTotalPrice'],flush=True)
