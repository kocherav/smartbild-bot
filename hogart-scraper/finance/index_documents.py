import json,subprocess,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parent;dest=ROOT/'evidence/document_text';dest.mkdir(exist_ok=True)
paths=set()
for base in [ROOT.parent/'incoming',Path('/home/kocher.av/megaplan-crm/report_sources'),ROOT/'evidence']:
 for p in base.rglob('*'):
  if p.is_file() and p.suffix.lower() in ('.pdf','.md','.txt'):paths.add(p)
index=[]
for p in sorted(paths):
 if dest in p.parents:continue
 if p.suffix.lower()=='.pdf':
  target=dest/(hashlib.sha256(str(p).encode()).hexdigest()+'.txt')
  if not target.exists():
   try:subprocess.run(['pdftotext','-layout',str(p),str(target)],capture_output=True,timeout=20)
   except subprocess.TimeoutExpired:continue
  if not target.exists():continue
  text=target.read_text(errors='replace')
 else:text=p.read_text(errors='replace')
 index.append({'path':str(p),'text':text})
(ROOT/'evidence/document_index.json').write_text(json.dumps(index,ensure_ascii=False));print('indexed',len(index))
