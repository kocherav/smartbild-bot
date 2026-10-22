import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'megaplan-crm'))
from procurement_projection import effective_registry
"""Versioned matching decisions, separate from purchase/financial allocations."""
import hashlib,json,os,sqlite3,time
from pathlib import Path
from contextlib import contextmanager
from product_matching import compare,VERSION
DB=Path(__file__).resolve().parent/'data/product-matching.sqlite3'

def candidate(deal,row,line,invoice):
 payload={'version':VERSION,'deal_id':str(deal),'row':{k:row.get(k) for k in ('id','name','quantity','unit')},'line':line,'invoice':{k:invoice.get(k) for k in ('id','number','date','supplier')}}
 key=hashlib.sha256(json.dumps(payload,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
 return key,payload

def candidates(deal,positions,registry):
 registry=effective_registry(registry)
 rows={str(r['id']):r for r in positions};result={}
 for inv in registry.get('invoices',[]):
  for alloc in inv.get('allocations',[]):
   if str(alloc.get('deal_id'))!=str(deal):continue
   for line in alloc.get('source_lines') or alloc.get('updates') or []:
    row=rows.get(str(line.get('offer_row_id')))
    if row:
     key,payload=candidate(deal,row,line,inv);result[key]=payload
 return result

@contextmanager
def connection(path=None):
 p=Path(path or DB);p.parent.mkdir(parents=True,exist_ok=True)
 db=sqlite3.connect(p,timeout=15);db.row_factory=sqlite3.Row
 try:
  db.executescript('CREATE TABLE IF NOT EXISTS decisions(id TEXT PRIMARY KEY,payload TEXT NOT NULL,state TEXT NOT NULL,result TEXT NOT NULL,updated REAL NOT NULL,attempts INTEGER NOT NULL DEFAULT 0); CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY,key TEXT,state TEXT,actor TEXT,at REAL,result TEXT);')
  if p.stat().st_uid==os.geteuid():p.chmod(0o660)
  with db:yield db
 finally:db.close()

def project(inputs,path=None):
 result={}
 with connection(path) as db:
  for key,payload in inputs.items():
   rule=compare(payload['row']['name'],payload['line'].get('source_name'))
   if rule['same']:continue
   initial='blocked' if rule['conflicts'] else 'queued'
   db.execute('INSERT OR IGNORE INTO decisions(id,payload,state,result,updated) VALUES(?,?,?,?,?)',(key,json.dumps(payload,ensure_ascii=False),initial,json.dumps({'reason':'; '.join(rule['conflicts'])}),time.time()))
   # Formatting-only rule upgrades keep reviewed decisions for identical input.
   # A formerly blocked pair whose conflict disappeared is reviewed afresh.
   if VERSION=='rules-2' and not rule['conflicts']:
    old_payload={**payload,'version':'rules-1'}
    old_key=hashlib.sha256(json.dumps(old_payload,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    old=db.execute('SELECT state,result FROM decisions WHERE id=?',(old_key,)).fetchone()
    if old and old['state'] in ('auto','accepted','review','rejected'):
     updated=db.execute("UPDATE decisions SET state=?,result=? WHERE id=? AND state='queued'",(old['state'],old['result'],key))
     if updated.rowcount:db.execute('INSERT INTO events(key,state,actor,at,result) VALUES(?,?,?,?,?)',(key,old['state'],'rules-2-format-migration',time.time(),old['result']))
   r=db.execute('SELECT * FROM decisions WHERE id=?',(key,)).fetchone()
   result[key]={'id':key,'state':r['state'],**json.loads(r['result'])}
 return result

def decide(key,action,actor,inputs,path=None):
 if key not in inputs:raise ValueError('Исходные данные изменились. Обновите пульт.')
 if action not in ('accepted','rejected'):raise ValueError('Неизвестное решение')
 rule=compare(inputs[key]['row']['name'],inputs[key]['line'].get('source_name'))
 if action=='accepted' and rule['conflicts']:raise ValueError('Есть противоречия характеристик: '+ '; '.join(rule['conflicts']))
 project({key:inputs[key]},path)
 with connection(path) as db:
  db.execute('BEGIN IMMEDIATE');r=db.execute('SELECT result FROM decisions WHERE id=?',(key,)).fetchone()
  if not r:raise ValueError('Для этой позиции решение не требуется')
  result={**json.loads(r['result']),'actor':str(actor),'human_reason':'Подтверждено пользователем' if action=='accepted' else 'Отклонено пользователем'}
  db.execute('UPDATE decisions SET state=?,result=?,updated=? WHERE id=?',(action,json.dumps(result,ensure_ascii=False),time.time(),key))
  db.execute('INSERT INTO events(key,state,actor,at,result) VALUES(?,?,?,?,?)',(key,action,str(actor),time.time(),json.dumps(result,ensure_ascii=False)))
 return {'ok':True}

def claim(path=None,limit=8):
 with connection(path) as db:
  db.execute('BEGIN IMMEDIATE')
  db.execute("UPDATE decisions SET state='error',result=?,updated=? WHERE state='processing' AND updated<?",(json.dumps({'reason':'Проверка прервана. Повтор через несколько минут.'}),time.time(),time.time()-600))
  rows=db.execute("SELECT * FROM decisions WHERE state='queued' OR (state='error' AND attempts<3 AND updated<?) ORDER BY updated LIMIT ?",(time.time()-300,limit)).fetchall()
  for r in rows:db.execute("UPDATE decisions SET state='processing',updated=?,attempts=attempts+1 WHERE id=?",(time.time(),r['id']))
  return [{'id':r['id'],'payload':json.loads(r['payload'])} for r in rows]

def finish(key,result,path=None):
 confidence=result.get('confidence')
 if isinstance(confidence,bool) or not isinstance(confidence,(int,float)) or not 0<=confidence<=100:raise ValueError('Неверная оценка ИИ')
 if not isinstance(result.get('same'),bool) or not isinstance(result.get('reason'),str) or not result['reason'].strip() or not isinstance(result.get('conflicts'),list) or any(not isinstance(x,str) for x in result.get('conflicts',[])):raise ValueError('Неверный ответ ИИ')
 with connection(path) as db:
  db.execute('BEGIN IMMEDIATE');r=db.execute('SELECT * FROM decisions WHERE id=?',(key,)).fetchone()
  if not r or r['state']!='processing':return # Never overwrite a concurrent human decision.
  p=json.loads(r['payload']);rule=compare(p['row']['name'],p['line'].get('source_name'))
  state='auto' if result['same'] and confidence>70 and not result['conflicts'] and not rule['conflicts'] else 'review'
  db.execute('UPDATE decisions SET state=?,result=?,updated=? WHERE id=?',(state,json.dumps(result,ensure_ascii=False),time.time(),key))
  db.execute('INSERT INTO events(key,state,actor,at,result) VALUES(?,?,?,?,?)',(key,state,'AI',time.time(),json.dumps(result,ensure_ascii=False)))

def fail(keys,path=None):
 with connection(path) as db:
  for key in keys:db.execute("UPDATE decisions SET state='error',result=?,updated=? WHERE id=? AND state='processing'",(json.dumps({'reason':'ИИ временно недоступен. Можно проверить счёт и принять решение вручную.'}),time.time(),key))
