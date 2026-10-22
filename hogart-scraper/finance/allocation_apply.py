"""Confirmed allocation execution in the existing review registry."""
import copy,datetime as dt,fcntl,hashlib,json,sys
from pathlib import Path
import allocation_workspace as workspace
import review_registry as queue
CRM=Path(__file__).resolve().parents[2]/'megaplan-crm'
sys.path.insert(0,str(CRM));sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'dashboard'))
from product_matching import compare

def ledger(deal):return json.loads((CRM/'ledger'/f'{deal}.json').read_text())

def targets(plan,entries,usage=None):
 usage=usage or {}
 from procurement_match import unit
 if not plan['allocations']:raise ValueError('Выберите хотя бы одну позицию для распределения')
 remaining={(did,str(e.get('offer_row_id'))):max(workspace.number(e.get('qty',0))-max(workspace.number(e.get('consumed_qty',0)),usage.get((did,str(e.get('offer_row_id'))),{}).get('qty',0)),0) for did,rows in entries.items() for e in rows}
 result=[]
 for part in plan['allocations']:
  qty=workspace.number(part['qty']);did=part['deal_id']
  hits=[e for e in entries[did] if e.get('offer_row_id') and e.get('offer_id') and remaining[(did,str(e['offer_row_id']))]>=qty and compare(part['name'],e['name'])['same'] and (not part.get('source_unit') or unit(part['source_unit'])==unit(e.get('unit')))]
  item={**part,'cost_kind':'expense','offer_id':None,'offer_row_id':None,'target_label':'Дополнительный расход сделки; позиции и сумма договора не изменяются'}
  if part.get('offer_row_id'):
   hits=[e for e in entries[did] if str(e.get('offer_row_id'))==str(part['offer_row_id']) and e.get('offer_id')]
   if len(hits)!=1:raise ValueError('Позиция сделки не найдена')
   qty=workspace.number(part.get('covered_qty',part['qty']))
   if qty<=0 or qty>remaining[(did,str(hits[0]['offer_row_id']))]:raise ValueError('Покрывается больше оставшегося количества позиции сделки')
   if part.get('identity_confirmed') is not True:raise ValueError('Подтвердите соответствие позиции и единиц измерения')
   if not str(part.get('reason','')).strip():raise ValueError('Укажите основание ручного сопоставления')
   item['covered_qty']=str(qty);item['identity_confirmed']=True;item['reason']=str(part['reason'])[:500]
  if len(hits)==1:
   e=hits[0];item.update(cost_kind='material',offer_id=str(e['offer_id']),offer_row_id=str(e['offer_row_id']),target_label='Закупка к позиции: '+e['name'])
   prior=usage.get((did,str(e['offer_row_id'])),{})
   item.update(prior_confirmed_qty=str(prior.get('qty',0)),prior_confirmed_cost=str(prior.get('cost',0)))
   remaining[(did,str(e['offer_row_id']))]-=qty
  result.append(item)
 return result

def prepare(body,deals,procurement,loader=ledger):
 plan=workspace.preview(body,deals,procurement)
 entries={did:loader(did) for did in {p['deal_id'] for p in plan['allocations']}}
 from procurement_usage import totals
 plan['targets']=targets(plan,entries,totals(procurement))
 plan['ledger_before']=entries
 plan['apply_revision']=workspace.fingerprint({'source':plan['source_revision'],'targets':plan['targets'],'ledgers':entries})
 return plan

def public(plan):return {k:v for k,v in plan.items() if k!='ledger_before'}

def request(body,deals,actor,root=queue.ROOT,procurement_path=queue.PROCUREMENT,loader=ledger):
 path=root/'data/review_registry.json'
 with path.with_suffix('.lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX);data=json.loads(path.read_text());old=data.get('allocation_drafts',{}).get(body.get('document_key'),{})
  execution=old.get('execution')
  if execution:
   if execution['plan']['apply_revision']==body.get('apply_revision'):
    if execution['state']=='error':
     execution['state']='queued';execution.pop('error',None);queue.atomic(path,data)
    return public_job(execution)
   if execution['state'] not in ('completed','superseded'):raise ValueError('Предыдущее распределение ещё обрабатывается')
  plan=prepare(body,deals,json.loads(procurement_path.read_text()),loader)
  if plan['apply_revision']!=body.get('apply_revision'):raise workspace.Conflict('Изменились данные. Повторите проверку сумм.')
  if body.get('draft_revision',0)!=old.get('revision',0):raise workspace.Conflict('Черновик изменился. Обновите страницу.')
  job={'id':plan['apply_revision'],'state':'queued','actor':str(actor),'plan':plan,'steps':{},'updated_at':dt.datetime.now(dt.timezone.utc).isoformat()}
  data.setdefault('allocation_drafts',{})[plan['document_key']]={**plan,'revision':old.get('revision',0)+1,'state':'confirmed','execution':job}
  data.setdefault('workflow_audit',[]).append({'action':'allocation_confirmed','id':job['id'],'actor':str(actor),'at':job['updated_at']})
  queue.atomic(path,data)
 return public_job(job)

def public_job(job):return {**job,'plan':public(job['plan'])}

def update(key,job,root=queue.ROOT):
 path=root/'data/review_registry.json'
 with path.with_suffix('.lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX);data=json.loads(path.read_text());draft=data['allocation_drafts'][key]
  if draft.get('execution',{}).get('id')!=job['id']:raise ValueError('Задание изменилось')
  job['updated_at']=dt.datetime.now(dt.timezone.utc).isoformat()
  draft['execution']=job;draft['state']=job['state'];draft['crm_applied']=job['state']=='completed'
  remaining=job.get('steps',{}).get('registry')
  if isinstance(remaining,dict):
   for sid,values in remaining.items():
    task=data.get('tasks',{}).get('stock:'+sid)
    if task:
     task.update(values,updated_at=job['updated_at'])
     if not values['qty'] and not values['amount_cents']:task.update(state='resolved',resolution='Остаток распределён подтверждением в пульте',execution_id=job['id'])
  data['updated_at']=job['updated_at']
  if job['state']=='completed' and not any(x.get('action')=='allocation_completed' and x.get('id')==job['id'] for x in data.get('workflow_audit',[])):
   data.setdefault('workflow_audit',[]).append({'action':'allocation_completed','id':job['id'],'document_key':key,'receipt':copy.deepcopy(job),'at':job['updated_at']})
  queue.atomic(path,data)

def commit(job,procurement_path=queue.PROCUREMENT,ledger_dir=None):
 from registry_transaction import locked
 import procurement_workflow
 ledger_dir=Path(ledger_dir or CRM/'ledger');plan=job['plan']
 with locked(procurement_path):
  data=json.loads(procurement_path.read_text());stocks={s['id']:s for s in data.get('unallocated_stock',[])}
  ids=[hashlib.sha256(f"{job['id']}:{i}".encode()).hexdigest()[:24] for i in range(len(plan['targets']))]
  done=[any(a.get('id')==ident for a in stocks[p['line_id']].get('allocations',[])) for ident,p in zip(ids,plan['targets'])]
  def receipt():return {part['line_id']:{'qty':stocks[part['line_id']]['available_qty'],'amount_cents':workspace.cents(stocks[part['line_id']]['available_amount'])} for part in plan['targets']}
  if all(done):return receipt()
  if any(done):raise ValueError('Неполная запись распределения требует сверки')
  if workspace.fingerprint(workspace.source_document(data,plan['document_key']))!=plan['source_revision']:raise ValueError('Остатки счёта изменились после подтверждения')
  remaining={sid:[workspace.number(s['available_qty']),workspace.cents(s['available_amount'])] for sid,s in stocks.items()}
  for part in plan['targets']:
   left=remaining[part['line_id']];left[0]-=workspace.number(part['qty']);left[1]-=part['amount_cents']
   if left[0]<0 or left[1]<0:raise ValueError('Недостаточно остатка счёта')
  after=copy.deepcopy(plan['ledger_before'])
  for part in plan['targets']:
   if part['cost_kind']!='material':continue
   e=next(e for e in after[part['deal_id']] if str(e.get('offer_row_id'))==part['offer_row_id'])
   e['consumed_qty']=float(max(workspace.number(e.get('consumed_qty',0)),workspace.number(part.get('prior_confirmed_qty',0)))+workspace.number(part.get('covered_qty',part['qty'])))
   e['cumulative_cost_material']=float(max(workspace.number(e.get('cumulative_cost_material',0)),workspace.number(part.get('prior_confirmed_cost',0)))+workspace.number(part['amount_cents'])/100)
   e['cost_material']=float(workspace.number(e['cumulative_cost_material'])/workspace.number(e['qty']));e['cost_material_basis']='unit';e['price_source']='supplier_invoice'
  # Absolute before/after values allow retry after a process dies between files.
  from contextlib import ExitStack
  with ExitStack() as stack:
   for did in sorted(after):stack.enter_context(locked(ledger_dir/f'{did}.json'))
   for did,rows in after.items():
    path=ledger_dir/f'{did}.json';current=json.loads(path.read_text())
    if current not in (plan['ledger_before'][did],rows):raise ValueError('Экономика сделки '+did+' изменена; требуется новая проверка')
   for did,rows in after.items():
    if rows!=plan['ledger_before'][did]:queue.atomic(ledger_dir/f'{did}.json',rows)
   for ident,part in zip(ids,plan['targets']):
    stock=stocks[part['line_id']];qty=workspace.number(part['qty']);amount=part['amount_cents']
    if qty>workspace.number(stock['available_qty']) or amount>workspace.cents(stock['available_amount']):raise ValueError('Недостаточно остатка счёта')
    stock['available_qty']=float(workspace.number(stock['available_qty'])-qty);stock['available_amount']=(workspace.cents(stock['available_amount'])-amount)/100
    stock.setdefault('allocations',[]).append({'id':ident,'deal_id':part['deal_id'],'offer_id':part['offer_id'],'offer_row_id':part['offer_row_id'],'cost_kind':part['cost_kind'],'qty':float(qty),'covered_qty':float(workspace.number(part.get('covered_qty',part['qty']))),'identity_confirmed':bool(part.get('identity_confirmed')),'reason':part.get('reason',''),'amount':amount/100,'actor':job['actor'],'created_at':dt.datetime.now(dt.timezone.utc).isoformat(),'job_id':job['id']})
    stock['status']='распределено' if not stock['available_qty'] else 'частично распределено'
   for did,rows in after.items():
    by_id={str(e.get('offer_row_id')):e for e in rows}
    record=data.setdefault('deals',{}).setdefault(did,{'deal_id':did,'items':[]})
    known={str(i.get('offer_row_id')) for i in record['items']}
    for e in rows:
     if str(e.get('offer_row_id')) not in known:
      record['items'].append({'offer_row_id':e.get('offer_row_id'),'offer_id':e.get('offer_id'),'name':e['name'],'qty':e.get('qty',0),'unit':e.get('unit',''),'received_qty':0,'planned_unit_cost':e.get('cost_material') or 0,'planned_total':float(workspace.number(e.get('cost_material') or 0)*workspace.number(e.get('qty',0)))})
    record['updated_at']=dt.datetime.now(dt.timezone.utc).isoformat()
    for item in record['items']:
     e=by_id.get(str(item.get('offer_row_id')))
     if e:item.update(actual_qty=e.get('consumed_qty',0),actual_total=e.get('cumulative_cost_material',0))
   data.setdefault('allocation_audit',[]).append({'action':'dashboard_allocation','id':job['id'],'targets':plan['targets'],'actor':job['actor']})
   procurement_workflow.reconcile_invoice_totals(data);queue.atomic(procurement_path,data)
   return receipt()
