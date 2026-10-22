"""Resumable application of dashboard-confirmed supplier cost allocations."""
import json,sys,subprocess,time
from pathlib import Path
BASE=Path(__file__).resolve().parent
sys.path.insert(0,str(BASE.parent/'hogart-scraper/finance'));sys.path.insert(0,str(BASE.parent/'megaplan-crm'))
import allocation_apply as flow

def money(value):
 if isinstance(value,dict):
  from financial_amounts import crm_money_in_main
  return flow.workspace.number(crm_money_in_main(value) or 0)
 return flow.workspace.number(value or 0)

def sync_deal(job,did,api):
 import deal_ledger
 import build_profitability_report as report
 live=api._call('GET','/deal/'+did)['data'];positions={str(x['id']):x for x in live.get('positions',[])}
 if any((r.get('price') or {}).get('currency') not in (None,'RUB') or (r.get('sum') or {}).get('currency') not in (None,'RUB') for r in positions.values()):
  raise ValueError('Сделка №'+did+': сначала зафиксируйте валютные цены продажи в рублях по согласованному договору или выставленному счёту. Изменение экономики не должно пересчитывать продажу по сегодняшнему курсу. Закупочная запись сохранена.')
 saved=deal_ledger.load(did);by_row={str(x.get('offer_row_id')):x for x in saved}
 for target in job['plan']['targets']:
  if target['deal_id']!=did or target['cost_kind']!='material':continue
  row=positions.get(target['offer_row_id']);entry=by_row[target['offer_row_id']]
  if not row or str((row.get('offer') or {}).get('id'))!=target['offer_id'] or money(row.get('quantity'))!=money(entry['qty']):raise ValueError('Состав сделки изменён. Нужна сверка позиции '+target['name'])
  expected=api._cost_fields(cost_material=entry['cost_material'],cost_work=None)
  offer=api._call('GET','/offer/'+target['offer_id'])['data']
  if any(abs(money(offer.get(k))-money(v))>flow.workspace.number('.01') for k,v in expected.items()):
   before=next(e for e in job['plan']['ledger_before'][did] if str(e.get('offer_row_id'))==target['offer_row_id'])
   baseline=api._cost_fields(cost_material=before.get('cost_material',0),cost_work=None)
   if any(abs(money(offer.get(k))-money(v))>flow.workspace.number('.01') for k,v in baseline.items()):raise ValueError('Себестоимость позиции изменена в Мегаплане; требуется сверка')
   api.update_offer_cost(target['offer_id'],cost_material=entry['cost_material'])
   offer=api._call('GET','/offer/'+target['offer_id'])['data']
  if any(abs(money(offer.get(k))-money(v))>flow.workspace.number('.01') for k,v in expected.items()):raise ValueError('Мегаплан не подтвердил себестоимость')
 live=api._call('GET','/deal/'+did)['data'];entries=api.ledger_from_deal(live,price_source='megaplan_live')
 for entry in entries:
  saved_row=by_row.get(str(entry.get('offer_row_id')),{})
  for key in ('cost_material_basis','cost_work_basis'):
   if key in saved_row:entry[key]=saved_row[key]
 revenue=sum(money(e.get('qty'))*money(e.get('sell_price')) for e in entries)
 if abs(revenue-money(live.get('price')))>flow.workspace.number('.01'):raise ValueError('Сделка №'+did+': сумма строк '+str(round(revenue,2))+' ₽ отличается от суммы сделки '+str(round(money(live.get('price')),2))+' ₽. Сверьте действующую спецификацию в Мегаплане, затем нажмите «Продолжить обработку». Уже распределённые закупки сохраняются.')
 import financial_amounts
 ambiguous=[(e,f) for e in entries for f in financial_amounts.audit_entry(did,e)]
 if ambiguous:
  e,f=ambiguous[0]
  raise ValueError('Сделка №'+did+', «'+e['name']+'»: проверьте базу себестоимости. Значение '+str(f['raw'])+' ₽ умножается на '+str(e['qty'])+'. Уточните цену за единицу в карточке позиции Мегаплана либо подтвердите стоимость всей строки, затем продолжите обработку. Закупки повторно не начисляются.')
 rows,total,cost,profit,margin=report.compute_profitability(entries,report.load_procurement_items(did),report.load_installation_items(did),did)
 field='Category1000068CustomFieldRentabelnost'
 expected=round(profit,2)
 if abs(money(live.get(field))-money(expected))>flow.workspace.number('.01'):
  api._call('POST','/deal/'+did,json_body={'contentType':'Deal',field:{'contentType':'Money','currency':'RUB','value':expected}})
 verified=api._call('GET','/deal/'+did)['data']
 if abs(money(verified.get('price'))-money(live.get('price')))>flow.workspace.number('.01'):
  raise ValueError('Сделка №'+did+': Мегаплан изменил сумму продажи при обновлении экономики: '+str(round(money(live.get('price')),2))+' → '+str(round(money(verified.get('price')),2))+' ₽. Нужна сверка валютного пересчёта в CRM; закупочная запись сохранена, повторное начисление запрещено.')
 if abs(money(verified.get(field))-money(expected))>flow.workspace.number('.01'):raise ValueError('Мегаплан не подтвердил рентабельность')
 return {'verified':True,'revenue':round(total,2),'cost':round(cost,2),'profit':expected,'cash_operations_changed':False}

def process(key,job,api,root=flow.queue.ROOT):
 try:
  job['state']='processing';flow.update(key,job,root)
  if not job['steps'].get('registry'):
   job['steps']['registry']=flow.commit(job);flow.update(key,job,root)
  for did in sorted({p['deal_id'] for p in job['plan']['targets']}):
   stage='crm:'+did
   if not job['steps'].get(stage):job['steps'][stage]=sync_deal(job,did,api);flow.update(key,job,root)
  job['state']='completed';job.pop('error',None)
 except Exception as exc:
  job['state']='error';job['error']=str(exc)[:500]
  if job.get('actor')=='automatic-procurement' and not job['steps'].get('registry') and str(exc)=='Остатки счёта изменились после подтверждения':
   job['state']='superseded' # Recompute candidates and amounts next cycle; no write has happened.
  elif any(text in str(exc).lower() for text in ('очередь запросов занята','запрос не отправлен','timed out','timeout')) and job.get('retry_attempts',0)<5:
   job['retry_attempts']=job.get('retry_attempts',0)+1;job['retry_at']=time.time()+min(900,60*2**(job['retry_attempts']-1));job['state']='queued'
 flow.update(key,job,root)

def poll():
 from megaplan_api import MegaplanAPI
 data=json.loads((flow.queue.ROOT/'data/review_registry.json').read_text())
 for key,draft in data.get('allocation_drafts',{}).items():
  job=draft.get('execution')
  if job and job['state'] in ('queued','processing') and job.get('retry_at',0)<=time.time():process(key,job,MegaplanAPI())

def poll_in_environment():
 subprocess.run([str(BASE.parent/'.report-venv/bin/python'),str(Path(__file__).resolve())],check=True,timeout=600)

if __name__=='__main__':poll()
