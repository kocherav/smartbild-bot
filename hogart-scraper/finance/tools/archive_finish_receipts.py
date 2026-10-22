import json,subprocess,hashlib
from pathlib import Path
R=Path(__file__).resolve().parents[1];D=R/'evidence/finish_all';out=[]
for uid,label,folder in [('66111','Яндекс360_2026-06-23_5391','00_Общехозяйственные/ИНСИС/ИТ_и_подписки'),('67420','Яндекс360_2026-09-20_10745','00_Общехозяйственные/ИНСИС/ИТ_и_подписки'),('67375','Huawei_предоплата_18000','00_Требует_распределения/Чеки_по_карте'),('67408','Huawei_зачёт_предоплаты_18000','00_Требует_распределения/Чеки_по_карте')]:
 for ext in ['json','txt']:
  p=D/'receipts'/('kav_83ecb521bf32_'+uid+'.'+ext);sha=hashlib.sha256(p.read_bytes()).hexdigest();remote=f'onedrive:SmartBild/Сделки/{folder}/{label}_{sha[:12]}.{ext}'
  subprocess.run(['rclone','copyto',str(p),remote,'--immutable'],capture_output=True,check=True,timeout=120)
  stat=json.loads(subprocess.check_output(['rclone','lsjson',remote,'--stat'],text=True));assert stat['Size']==p.stat().st_size
  out.append(dict(source=str(p),sha256=sha,remote=remote,verified=True));(D/'receipt_archive.json').write_text(json.dumps(out,ensure_ascii=False,indent=2));print(label,ext,flush=True)
