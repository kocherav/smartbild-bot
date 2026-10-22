import json,hashlib,subprocess
from pathlib import Path
D=Path(__file__).resolve().parents[1]/'evidence/final_answers_20261007';result=[]
for x in json.loads((D/'outside_archive_links.json').read_text()):
 p=Path(x['source']);sha=hashlib.sha256(p.read_bytes()).hexdigest();remote='onedrive:SmartBild/Финансы/ИНСИС/2026/'+x['scope']+'/Счёт '+x['number']+'_'+sha[:12]+p.suffix
 subprocess.run(['rclone','copyto',str(p),remote,'--immutable'],check=True,capture_output=True,timeout=120);v=json.loads(subprocess.check_output(['rclone','lsjson',remote,'--stat'],text=True));assert v['Size']==p.stat().st_size;result.append({**x,'remote':remote,'sha256':sha,'verified':True});(D/'outside_archive_results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print(x['number'],'verified',flush=True)
