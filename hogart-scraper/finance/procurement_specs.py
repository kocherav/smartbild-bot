"""Read CRM specifications before matching; preserve confirmed local allocations."""
import copy,json,time,sys
from pathlib import Path
import review_registry as queue
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'megaplan-crm'))
from registry_transaction import locked
from megaplan_api import MegaplanAPI, MegaplanAPIError
import deal_ledger

def merge(deal,old,units):
 live=MegaplanAPI.ledger_from_deal(deal,price_source='megaplan_live')
 previous={str(r['offer_row_id']):r for r in old if r.get('offer_row_id')}
 ids={str(r['offer_row_id']) for r in live}
 if any(str(r.get('offer_row_id')) not in ids and (r.get('consumed_qty') or r.get('cumulative_cost_material')) for r in old):
  raise ValueError('В CRM удалена позиция с распределёнными закупками; требуется сверка состава')
 result=[]
 for r in live:
  before=previous.get(str(r['offer_row_id']),{})
  if before and str(before.get('offer_id'))!=str(r['offer_id']):raise ValueError('В CRM заменена номенклатура позиции; требуется сверка')
  if float(before.get('consumed_qty') or 0)>r['qty']:raise ValueError('Количество CRM меньше уже распределённого; требуется сверка')
  r['unit']=r.get('unit') or units.get(str(r.get('unit_id')),'')
  if not r['unit']:raise ValueError('В CRM не указана единица позиции '+r['name'])
  value={**copy.deepcopy(before),**r}
  # These cumulative facts have no direct representation in the CRM row.
  for k in ('consumed_qty','cumulative_cost_material','cumulative_cost_work'):
   if k in before:value[k]=before[k]
  # CRM numeric fields do not encode whether historic values were per unit or
  # per line. Refresh must not erase an explicitly established interpretation.
  value['cost_material_basis']=before.get('cost_material_basis','unit')
  value['cost_work_basis']=before.get('cost_work_basis','unit')
  result.append(value)
 return result

def request(did,root=queue.ROOT):
 did=str(did)
 if not did.isdigit():raise ValueError('Выберите сделку')
 p=root/'data/review_registry.json'
 with locked(p):
  data=queue.read(p,{});data.setdefault('procurement_specs',{})[did]={'state':'queued','attempts':0,'updated':time.time()};queue.atomic(p,data)
 return {'ok':True,'state':'queued'}

def refresh(api=None,limit=4,root=queue.ROOT,procurement_path=queue.PROCUREMENT,ledger_dir=None,now=None):
 now=now or time.time();api=api or MegaplanAPI();ledger_dir=Path(ledger_dir or deal_ledger.LEDGER_DIR)
 raw=queue.read(procurement_path,{});p=root/'data/review_registry.json';reg=queue.read(p,{})
 ids={str(d) for i in raw.get('invoices',[]) for d in i.get('candidate_deal_ids',[])}|set(reg.get('procurement_specs',{}))
 busy={str(t['deal_id']) for d in reg.get('allocation_drafts',{}).values() if d.get('execution',{}).get('state') in ('queued','processing','error') for t in d['execution']['plan']['targets']}
 jobs=[]
 for did in sorted(ids):
  if did in busy:continue
  s=reg.get('procurement_specs',{}).get(did,{})
  if s.get('state')=='error' and (s.get('attempts',0)>=3 or now-s.get('updated',0)<300):continue
  if s.get('state')=='ready' and now-s.get('updated',0)<3600 and (ledger_dir/f'{did}.json').exists():continue
  jobs.append(did)
 jobs.sort(key=lambda d:((ledger_dir/f'{d}.json').exists(),reg.get('procurement_specs',{}).get(d,{}).get('updated',0)))
 units=None;results={}
 for did in jobs[:limit]:
  path=ledger_dir/f'{did}.json';old=queue.read(path,[])
  try:
   deal=api._call('GET','/deal/'+did)['data']
   if units is None:units={str(u['id']):u.get('name','') for u in api._call('GET','/unit')['data']}
   rows=merge(deal,old,units)
   with locked(procurement_path),locked(p),locked(path):
    current=queue.read(p,{})
    active={str(t['deal_id']) for d in current.get('allocation_drafts',{}).values() if d.get('execution',{}).get('state') in ('queued','processing','error') for t in d['execution']['plan']['targets']}
    if did in active or queue.read(path,[])!=old:raise ValueError('Распределение изменилось во время загрузки; повторите обновление')
    queue.atomic(path,rows)
   if ledger_dir==Path(deal_ledger.LEDGER_DIR):
    from procurement_workflow import snapshot
    snapshot(did)
   state={'state':'ready','rows':len(rows),'updated':now,'attempts':0,'error':'' if rows else 'В Мегаплане нет позиций сделки. Заполните спецификацию и обновите.'}
  except Exception as exc:
   error=str(exc)[:500]
   if isinstance(exc,MegaplanAPIError):error=('Сделка №'+did+' недоступна в Мегаплане. Проверьте наличие сделки и доступ; закупки не перенесены.') if exc.status==404 else 'Мегаплан отклонил загрузку спецификации (код '+str(exc.status)+'). Проверьте доступ и повторите обновление.'
   state={'state':'error','updated':now,'attempts':reg.get('procurement_specs',{}).get(did,{}).get('attempts',0)+1,'error':error}
  with locked(p):
   current=queue.read(p,{});current.setdefault('procurement_specs',{})[did]=state;queue.atomic(p,current)
  results[did]=state
 return results
