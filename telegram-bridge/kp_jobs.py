"""Retain deterministic proposal jobs, including failures and their original specification."""
import hashlib,json,time
from pathlib import Path
import durable_json

def run(spec, chat, directory, execute):
 root=Path(directory);root.mkdir(parents=True,exist_ok=True)
 ident=hashlib.sha256((str(chat)+json.dumps(spec,sort_keys=True,ensure_ascii=False)).encode()).hexdigest()[:24]
 path=root/(ident+'.json');source=root/(ident+'.spec.json')
 durable_json.save(str(source),spec)
 state={'id':ident,'chat_id':str(chat),'spec':spec,'updated_at':time.time(),'status':'building'}
 durable_json.save(str(path),state)
 try:
  result=execute(str(source))
  try:parsed=json.loads(result.stdout.strip().splitlines()[-1])
  except (ValueError,IndexError):parsed={'ok':False,'error':'Сборка КП завершилась технической ошибкой. Задание сохранено; можно написать «Повтори КП».'}
  if not isinstance(parsed,dict):parsed={'ok':False,'error':'Неверный формат результата сборки КП. Задание сохранено.'}
  if parsed.get('ok'):
   if result.returncode or not isinstance(parsed.get('variants'),list) or not parsed['variants'] or any(not isinstance(parsed.get(k),str) or not Path(parsed[k]).is_file() or not Path(parsed[k]).stat().st_size for k in ['path','economics_xlsx_path']):
    parsed={'ok':False,'error':'Не получены оба готовых файла КП и экономики. Задание сохранено; напишите «Повтори КП».'}
  state['diagnostic']=(result.stderr or '')[-4000:]
 except Exception as exc:
  parsed={'ok':False,'error':'Не удалось завершить сборку КП. Задание сохранено; напишите «Повтори КП».'};state['diagnostic']=type(exc).__name__
 state.update(status='ready' if parsed.get('ok') else 'failed',result=parsed,updated_at=time.time());durable_json.save(str(path),state)
 return parsed

def latest_failed(chat,directory):
 jobs=[]
 for path in Path(directory).glob('*.json'):
  if path.name.endswith('.spec.json'):continue
  d=durable_json.read(str(path),dict)
  if d.get('chat_id')==str(chat):jobs.append(d)
 latest=max(jobs,key=lambda x:x.get('updated_at',0),default=None)
 return latest if latest and latest.get('status')=='failed' else None
