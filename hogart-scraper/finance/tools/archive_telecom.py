import json,subprocess,hashlib
from pathlib import Path
R=Path(__file__).resolve().parents[1];D=R/'evidence/remaining_oct6'
sources=[(x['path'],'ВестКолл') for x in json.loads((D/'telecom_documents.json').read_text())]
sources += [(str(R/'evidence/kav'/n),label) for n,label in [('4558c516c01d09c07e6e1b73300d4d90279d942f32c0dc1684e3f4a738cf4d48.pdf','МегаФон_май2026'),('bb6e391471ce4f738089be2e176914255900d29a256815df30daa81c941ac2bf.pdf','МегаФон_июль2026')]]
out=[]
for src,label in sources:
 p=Path(src);sha=hashlib.sha256(p.read_bytes()).hexdigest();remote=f'onedrive:SmartBild/Сделки/00_Общехозяйственные/ИНСИС/Связь/{label}_{sha[:12]}.pdf'
 subprocess.run(['rclone','copyto',str(p),remote,'--immutable'],capture_output=True,check=True,timeout=120)
 stat=json.loads(subprocess.check_output(['rclone','lsjson',remote,'--stat'],text=True));assert stat['Size']==p.stat().st_size
 out.append(dict(source=str(p),sha256=sha,remote=remote,verified=True));print(label,sha[:12],flush=True)
(D/'telecom_archive.json').write_text(json.dumps(out,ensure_ascii=False,indent=2))
