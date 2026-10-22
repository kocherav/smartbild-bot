"""Commands for supplier documents share the existing review queue."""
import base64,fcntl,hashlib,json,time
from pathlib import Path
import allocation_workspace as aw
import allocation_apply as apply
import procurement_intake as intake
import procurement_match as match
import review_registry as queue

def ledgers(deals,loader=apply.ledger):
 rows={};errors={}
 for d in deals:
  if d.get('is_purchase'):continue
  did=str(d['id'])
  try:
   rows[did]=loader(did)
   if not rows[did]:errors[did]='В сделке нет загруженных позиций'
  except (OSError,ValueError):errors[did]='Спецификация сделки ещё не загружена'
 return rows,errors

def projection(deals,root=queue.ROOT,procurement_path=queue.PROCUREMENT,loader=apply.ledger,matching_path=None):
 result=aw.projection(deals,root,procurement_path);raw=intake.read(procurement_path,{})
 rows,errors=ledgers(deals,loader)
 from procurement_usage import totals
 usage=totals(raw)
 for did,es in rows.items():
  for e in es:
   e['consumed_qty']=float(max(aw.number(e.get('consumed_qty',0)),usage.get((did,str(e.get('offer_row_id'))),{}).get('qty',0)))
 result['positions']={did:[{k:e.get(k) for k in ('offer_row_id','name','qty','unit','consumed_qty')} for e in es if e.get('offer_row_id')] for did,es in rows.items()}
 statuses=intake.read(root/'data/review_registry.json',{}).get('procurement_specs',{})
 for did,st in statuses.items():
  if st.get('state')!='ready' or st.get('error'):errors[did]=st.get('error') or 'Обновление спецификации ожидает обработки'
 result['specification_status']=statuses
 result['position_errors']=errors;result['suggestions']=match.suggestions(raw,rows,matching_path)
 result['commands']={k:{a:b for a,b in v.items() if a!='payload'} for k,v in intake.read(root/'data/review_registry.json',{}).get('procurement_commands',{}).items()}
 result['explanation']='Сохраните черновик или подтвердите распределение. Выберите счёт и строки. Для каждой строки укажите сделку, позицию и количество. Проверьте расчёт и подтвердите распределение. Оплаты повторно не создаются.'
 return result

def command(body,actor,root=queue.ROOT,procurement_path=queue.PROCUREMENT):
 action=body.get('action');key=body.get('document_key')
 if action=='refresh_spec':
  import procurement_specs
  return procurement_specs.request(body.get('deal_id'),root)
 if action not in ('retry','manual_lines','upload','choose_version','new','repair_usage'):raise ValueError('Неизвестное действие')
 raw=intake.read(procurement_path,{})
 inv=next((i for i in raw.get('invoices',[]) if i['document_key']==key),None)
 if not inv and action!='new':raise ValueError('Счёт не найден')
 if inv and inv.get('intake',{}).get('state') in ('version_review','superseded') and action!='choose_version':raise ValueError('Сначала выберите действующую версию счёта. Откройте её карточку в списке счетов.')
 payload={}
 if action=='repair_usage':
  if not isinstance(body.get('mappings'),dict):raise ValueError('Укажите строки прежних распределений')
  payload={'mappings':body['mappings']}
 if action=='manual_lines':
  parsed={'lines':body.get('lines'),'total_cents':body.get('total_cents'),'date':body.get('date','')};intake.validate(parsed,{'amount_cents':aw.cents(inv['total'])} if inv.get('total') else {})
  payload={'parsed':parsed}
 if action in ('upload','new'):
  suffix=Path(str(body.get('filename',''))).suffix.lower()
  if suffix not in ('.pdf','.xls','.xlsx','.docx'):raise ValueError('Нужен PDF, XLS, XLSX или DOCX')
  try:content=base64.b64decode(body.get('content',''),validate=True)
  except Exception:raise ValueError('Файл повреждён') from None
  if not 1<=len(content)<=15*1024*1024:raise ValueError('Допустимый размер файла — до 15 МБ')
  folder=root/'data/supplier_uploads';folder.mkdir(parents=True,exist_ok=True);folder.chmod(0o770)
  sha=hashlib.sha256(content).hexdigest();path=folder/(sha+suffix)
  if not path.exists():path.write_bytes(content);path.chmod(0o660)
  payload={'path':str(path),'sha256':sha}
  if action=='new':
   inn=str(body.get('supplier_inn',''));number=str(body.get('number','')).strip();buyer=str(body.get('buyer_inn',''));deal=str(body.get('deal_id',''))
   if not inn.isdigit() or len(inn) not in (10,12) or not number or len(number)>100:raise ValueError('Укажите номер счёта и ИНН поставщика')
   if buyer not in ('7743926877','7743151323'):raise ValueError('Выберите компанию-покупателя')
   if not deal.isdigit():raise ValueError('Выберите сделку')
   meta={'source':str(path),'sha256':sha,'number':number,'supplier_inn':inn,'buyer_inn':buyer,'deal_ids':[deal]}
   key=intake.digest(inn+'|'+number+'|'+sha);payload['meta']=meta
 revision=aw.fingerprint(aw.source_document(raw,key)) if action!='new' else 'new'
 if action!='new' and body.get('source_revision')!=revision:raise aw.Conflict('Счёт изменился. Обновите страницу.')
 path=root/'data/review_registry.json'
 with path.with_suffix('.lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX);data=intake.read(path,{})
  previous=data.get('procurement_commands',{}).get(key)
  if previous and previous['state'] in ('queued','processing'):return previous
  job={'id':intake.digest(key+action+str(time.time_ns())),'action':action,'document_key':key,'source_revision':revision,'actor':str(actor),'payload':payload,'state':'queued','updated_at':time.time()}
  data.setdefault('procurement_commands',{})[key]=job;queue.atomic(path,data)
 return {k:v for k,v in job.items() if k!='payload'}

def finish(job,root=queue.ROOT):
 path=root/'data/review_registry.json'
 with path.with_suffix('.lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX);data=intake.read(path,{})
  data.setdefault('procurement_commands',{})[job['document_key']]=job
  data.setdefault('workflow_audit',[]).append({'action':'procurement_command','job':job});queue.atomic(path,data)
