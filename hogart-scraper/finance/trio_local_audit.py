import json,subprocess,hashlib
from pathlib import Path
root=Path(__file__).resolve().parent/'evidence/trio_local_audit';root.mkdir(exist_ok=True)
result=[]
for folder in ['/home/kocher.av/.cloudcli/assets','/home/kocher.av/hogart-scraper/incoming']:
 for p in Path(folder).glob('*.pdf'):
  key=hashlib.sha256(p.read_bytes()).hexdigest();target=root/(key+'.txt')
  if not target.exists():
   try:r=subprocess.run(['pdftotext','-layout',str(p),str(target)],capture_output=True,timeout=15)
   except subprocess.TimeoutExpired:continue
  if not target.exists():continue
  t=target.read_text(errors='replace')
  if '7717632694' in t and any(n in t for n in ['42965','44245','44472','45575','50605','55512']):result.append({'source':str(p),'text_path':str(target),'text':t})
(root/'matches.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print('matching sources',len(result))
for r in result:print(r['source'])
