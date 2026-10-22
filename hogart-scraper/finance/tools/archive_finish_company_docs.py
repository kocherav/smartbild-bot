import json,re,subprocess,hashlib
from pathlib import Path
R=Path(__file__).resolve().parents[1];D=R/'evidence/finish_all';out=[];seen=set()
for d in json.loads((R/'evidence/kav/documents.json').read_text()):
 t=d.get('text','')
 if '7734268607' not in t or '7743151323' not in t:continue
 match=re.search(r'Счет на оплату №\s*(\d+)',t)
 if not match:continue
 p=Path(d['path']);sha=hashlib.sha256(p.read_bytes()).hexdigest()
 if sha in seen:continue
 seen.add(sha);remote=f'onedrive:SmartBild/Сделки/00_Общехозяйственные/КЛИВЭЛ/Членские_взносы/СРО_{match[1]}_{sha[:12]}.pdf'
 subprocess.run(['rclone','copyto',str(p),remote,'--immutable'],capture_output=True,check=True,timeout=120)
 stat=json.loads(subprocess.check_output(['rclone','lsjson',remote,'--stat'],text=True));assert stat['Size']==p.stat().st_size
 out.append(dict(number=match[1],source=str(p),sha256=sha,remote=remote,verified=True));(D/'company_document_archive.json').write_text(json.dumps(out,ensure_ascii=False,indent=2));print(match[1],flush=True)
