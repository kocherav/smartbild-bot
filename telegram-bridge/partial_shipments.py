"""Bridge worker for owner-confirmed dashboard shipments."""
import copy, hashlib, json, sys
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'hogart-scraper/dashboard'))
import shipment_workspace as workspace


def round_document_rows(data):
 """Allocate only subkopeck rounding, preserving the agreed deal total exactly."""
 rows=data['positions'];raw=[Decimal(str(r['total'])) for r in rows]
 target=Decimal(str(data['total'])).quantize(Decimal('.01'),rounding=ROUND_HALF_UP)
 if sum(raw).quantize(Decimal('.01'),rounding=ROUND_HALF_UP)!=target:
  raise ValueError('Итог позиций отличается от согласованной суммы сделки')
 rounded=[x.quantize(Decimal('.01'),rounding=ROUND_HALF_UP) for x in raw]
 remainder=int((target-sum(rounded))*100)
 order=sorted(range(len(rows)),key=lambda i:raw[i]-rounded[i],reverse=remainder>0)
 if abs(remainder)>len(rows):raise ValueError('Расхождение суммы не является округлением копеек')
 for i in order[:abs(remainder)]:rounded[i]+=Decimal('.01') if remainder>0 else Decimal('-.01')
 for row,amount in zip(rows,rounded):
  row['total']=format(amount,'.2f')
  row['unit_price']=str(amount/Decimal(str(row['quantity'])))
 return data


def document_payer(payer):
 # Only document/settlement identity belongs in the approval fingerprint.
 # CRM embeds staff lastOnline inside contractor; viewing CRM must not invalidate approval.
 keys=('id','name','inn','kpp','legalAddress','currentAccount','bank','bik','correspondentAccount','ogrn','ogrnip')
 result={k:copy.deepcopy(payer[k]) for k in keys if k in payer}
 result['contractor']={'id':str((payer.get('contractor') or {}).get('id') or '')}
 return result


def snapshot(deal_id,crm):
 from generate_contract import contract_data
 from payer_signatory_store import get_signatory
 from seller_documents import selected_seller
 from document_tax_policy import row_rates,decorate,contract_positions,company_rate,settings
 from contract_invoice import latest_contract,document_text,contract_scope,specification_text
 from closing_documents import validate_contract_rows
 deal=crm._call('GET',f'/deal/{deal_id}')['data'];payer=str((deal.get('payer') or {}).get('id') or '')
 if not payer:raise ValueError('В сделке не выбран плательщик')
 deal['payer']=crm._call('GET','/payer/'+payer)['data']
 data=contract_data(deal,{'customer_signatory':get_signatory(payer),'customer_signatory_payer_id':payer})
 errors=[]
 if data['missing']:errors.append('Заполните реквизиты: '+', '.join(data['missing']))
 seller=selected_seller(str(deal_id))
 if seller['id'] not in ('cliwell','kocherzhinsky_ip'):raise ValueError('Для продавца ещё не утверждён шаблон акта')
 data.update(seller=seller,contract_date_iso=datetime.strptime(data['date'],'%d.%m.%Y').date().isoformat(),contract_file_id=None,contract_sha256=None)
 decorate(data,row_rates(deal,crm))
 path=None
 try:
  selected,path=latest_contract(crm,str(deal_id),context={'number':data['number'],'seller_inn':seller['inn'],'payer_inn':deal['payer']['inn']})
  text=document_text(path)
  from work_contract_scope import apply as apply_work_scope
  data=apply_work_scope(data,text)
  data.update(contract_file_id=str(selected['id']),contract_filename=selected['name'],contract_sha256=hashlib.sha256(Path(path).read_bytes()).hexdigest())
  scope=contract_scope(contract_positions(data['positions'],deal_id),deal_id)
  contract_total=sum(Decimal(str(r['total'])) for r in scope)
  data['contract_total']=str(contract_total)
  data['supplemental_total']=str(Decimal(str(data['total']))-contract_total)
  import re
  found=re.search(r'Цена договора[\s\S]{0,100}?составляет[\s:]*([\d \u00a0]+[,.]\d{2})\s*руб',text,re.I)
  if found:
   amount=Decimal(found[1].replace(' ','').replace('\u00a0','').replace(',','.'))
   if amount!=contract_total:errors.append(f"Сумма договора {amount:,.2f} ₽ не совпадает с суммой сделки {contract_total:,.2f} ₽. Нужна согласованная редакция договора/спецификации.")
  try:
   validate_contract_rows(specification_text(text,deal_id),scope)
  except ValueError as exc:errors.append(str(exc))
 except ValueError as exc:errors.append(str(exc))
 finally:
  if path:Path(path).unlink(missing_ok=True)
 round_document_rows(data)
 decorate(data)
 data['payer']=document_payer(data['payer'])
 data['blocking_errors']=errors
 data['tax_policy_rate']=company_rate(seller['id'])
 data['tax_policy']=settings().get('companies',{}).get(seller['id'],[])
 return data


def validate(job,crm):
 current=snapshot(job['deal_id'],crm)
 if current.get('blocking_errors'):raise ValueError('; '.join(current['blocking_errors']))
 if workspace.digest(current)!=job['shipment']['fingerprint']:
  raise ValueError('Договор, позиции или стороны изменились после подтверждения частичной передачи')
 return crm._call('GET',f"/deal/{job['deal_id']}")['data']


def import_full_jobs():
 """Prevent shipping quantities already transferred by the previous full workflow."""
 import closing_runtime as c
 for j in c.registry().read()['jobs'].values():
  if j.get('mode')!='live' or j.get('shipment_id') or j.get('status') not in ('ready','awaiting_edo','needs_info','edo_evidence_pending','edo_confirmed','awaiting_payment','completed') or not j.get('data',{}).get('positions'):continue
  ident='full-'+j['deal_id']
  previous=workspace.shipments(j['deal_id'])
  if any(x['id']==ident for x in previous):continue
  if previous:raise ValueError('Полный старый комплект пересекается с частичными отгрузками')
  rows=[{**r,'source_id':str(r['id']),'source_quantity':str(r['quantity'])} for r in j['data']['positions']]
  with workspace.connection() as db:
   db.execute('INSERT OR IGNORE INTO shipments VALUES(?,?,?,?,?,?)',(ident,j['deal_id'],0,'legacy_full',json.dumps({'positions':rows,'total':str(j['data']['total']),'act_number':j['data'].get('act_number') or j['deal_id']+'-АПП','job_id':j['id'],'finance':j.get('shipment_finance')},ensure_ascii=False),__import__('time').time()))


def poll():
 import closing_runtime as c
 if not (c.BASE/'partial_shipments.enabled').exists():return
 import_full_jobs()
 queue_remainders()
 for deal in workspace.pending_books():
  try:workspace.save_book(deal,snapshot(deal,c.api()))
  except Exception as exc:workspace.save_book(deal,error=str(exc) if isinstance(exc,ValueError) else type(exc).__name__)
 for s in workspace.shipments():
  if s['state']!='confirmed':continue
  j={'id':s['id'],'shipment_id':s['id'],'deal_id':s['deal'],'mode':'live','status':'preparing','created_at':c.now().isoformat(),'receipts':{},'shipment':s['payload']}
  c.registry().change(lambda d,j=j:d['jobs'].setdefault(j['id'],j))
  workspace.patch(s['id'],state='processing',values={'job_id':s['id']})
 # Project receipts, not guesses based on document creation.
 for s in workspace.shipments():
  if s['state'] in ('cancelled','confirmed'):continue
  j=c.registry().read()['jobs'].get(s['payload'].get('job_id',s['id']))
  if j:workspace.patch(s['id'],state='legacy_full' if s['state']=='legacy_full' else j['status'],values={'lifecycle':j['status'],'error':j.get('last_error'),'finance':j.get('shipment_finance'),'edo':j.get('edo_confirmation'),'receipts':j.get('receipts',{})})


def apply(job,data):
 from document_tax_policy import decorate,company_rate
 p=job['shipment'];rows=p['positions'];day=datetime.strptime(p['transfer_date'],'%d.%m.%Y').date().isoformat()
 expected=company_rate(data['seller']['id'],day)
 if expected is not None and any(int(r['tax_rate'])!=expected for r in rows):raise ValueError('Дата передачи не соответствует ставке НДС выбранных позиций')
 result=copy.deepcopy(data)
 result.update(positions=rows,total=p['total'],act_number=p['act_number'],act_date=p['transfer_date'],partial=True,transfer_dates={'goods':p['transfer_date'],'work':p['transfer_date']},partial_payment=p.get('payment') or {})
 decorate(result)
 return result


def payment_context(job,text):
 """A partial transfer never implicitly requests the contract's final invoice."""
 import re
 p=job['shipment'].get('payment') or {}
 rates={int(r['tax_rate']) for r in job['shipment']['positions']}
 if p and len(rates)!=1:raise ValueError('Для частичного счёта со смешанными ставками нужна разбивка суммы по ставкам')
 if p and not re.search(r'(?m)^\s*'+re.escape(p['clause'])+r'(?:[.\s])',text):
  raise ValueError('Указанный пункт частичного платежа не найден в договоре')
 result={'amount':str(p.get('amount') or '0.00'),'clause':p.get('clause') or '',
         'basis':p.get('basis') or '', 'line':('Частичный расчёт по акту '+job['shipment']['act_number']+'. '+p['basis']) if p else '',
         'tax_rate':next(iter(rates)) if len(rates)==1 else None,
         'transfer_date':job['shipment']['transfer_date']}
 result['fingerprint']=workspace.digest(result)
 return result


def payment_summary(deal):
 # Same native cash/bank projection as the dashboard; never count goods as cash.
 from model import project
 result=project({'deals':[deal],'invoices':[],'domain':'local','synced_at':''})['deals'][0]
 if not result['payments_complete']:raise ValueError('Не удалось сверить все оплаты сделки для подсказки бухгалтеру')
 return result['received'],[{'source':'megaplan','operation_id':x['id'],'amount_cents':x['amount'],'category':x['category']} for x in result['payments'] if x['category'] in ('client','client_refund')]


def all_edo(job):
 import closing_runtime as c
 ss=workspace.shipments(job['deal_id'])
 if not workspace.complete_volume(job['deal_id']):return False
 jobs=c.registry().read()['jobs']
 return all(jobs.get(s['payload'].get('job_id',s['id']),{}).get('edo_confirmation') and jobs.get(s['payload'].get('job_id',s['id']),{}).get('shipment_finance',{}).get('ok') for s in ss if s['state']!='cancelled')


def partial_invoice_text(data):
 number=str(data.get('number') or '').strip()
 day=str(data.get('date') or '').strip()
 if not number or not day:raise ValueError('Для частичного счёта нужны номер и дата договора')
 datetime.strptime(day,'%d.%m.%Y')
 basis=f'Договор № {number} от {day}'
 payment=data['partial_payment']
 line=f"Частичная оплата по акту № {data['act_number']}, п. {payment['clause']}. Основание: {basis}"
 extra=' '.join(str(payment.get('basis') or '').split())
 if extra and extra.casefold() not in ('договор',basis.casefold()):line+='; '+extra
 return line,basis


def reconcile_partial_invoice(job, crm, line, tax, basis=None):
 import closing_runtime as c
 from contract_invoice import normalized_invoice_text, verify_created_invoice
 receipt = (job.get('receipts') or {}).get('create-partial-invoice') or {}
 ident = receipt.get('_operation_id')
 if not ident:return
 store = c.WorkflowStore(c.DB); operation = store.get(ident)
 if operation['status'] != 'uncertain':return
 deal = crm._call('GET', '/deal/'+str(job['deal_id']), params={'fields':['invoices']})['data']
 candidates=[]
 for ref in deal.get('invoices') or []:
  inv=crm._call('GET', '/invoice/'+str(ref['id']), params={'fields':['rows']})['data']
  if any(normalized_invoice_text(r.get('name'))==normalized_invoice_text(line) for r in inv.get('rows') or []):candidates.append(inv)
 if len(candidates)!=1:
  raise ValueError('Сверка частичного счёта: найдено '+str(len(candidates))+' счетов с этим актом и основанием. Повторное создание остановлено до проверки состава счетов сделки.')
 data={'deal_id':job['deal_id'],'payer_id':job['data']['payer_id'],'basis':basis or line}
 rows=[{'name':line,'quantity':1,'price':str(job['data']['partial_payment']['amount']),'tax_id':tax}]
 inv=verify_created_invoice(crm,str(candidates[0]['id']),data,rows)
 result={'ok':True,'invoice_id':str(inv['id']),'number':str(inv['number'])}
 store.reconcile(ident,operation['revision'],'verified-partial-invoice-recovery','succeeded',
                 'CRM read-back: unique invoice '+str(inv['id'])+'; deal, payer, recipient, template, issued status, basis, rows, tax and RUB total verified',result)


def invoice(job,crm):
 import closing_runtime as c
 from contract_invoice import payment_offer,create_v1_invoice
 p=job['data'].get('partial_payment') or {}
 if not p:return None
 rates={int(r['tax_rate']) for r in job['data']['positions']}
 if len(rates)!=1:raise ValueError('Для частичного счёта со смешанными ставками нужна разбивка суммы по ставкам')
 rate=next(iter(rates));tax=str(crm.resolve_tax_id('none' if rate==-1 else str(rate)))
 line,basis=partial_invoice_text(job['data'])
 def create():
  offer=payment_offer(crm,line,tax)
  inv=create_v1_invoice(crm,{'deal_id':job['deal_id'],'payer_id':job['data']['payer_id'],'basis':basis or line},[{'name':line,'quantity':1,'price':str(p['amount']),'offer_id':offer['id'],'tax_id':tax}])
  return {'ok':True,'invoice_id':str(inv['id']),'number':str(inv['number'])}
 reconcile_partial_invoice(job,crm,line,tax,basis)
 receipt=c.effect(job,'create-partial-invoice',create);c.registry().patch(job['id'],invoice=receipt)
 import subprocess,shutil
 result=subprocess.run([sys.executable,str(c.CRM/'megaplan_webhook.py'),'fetch-invoice-pdf'],input=json.dumps({'invoiceId':receipt['invoice_id']}),capture_output=True,text=True,timeout=90)
 fetched=json.loads(result.stdout.strip().splitlines()[-1])
 if not fetched.get('ok'):raise ValueError('Не получен PDF частичного счёта')
 path=Path(job['folder'])/('Счёт '+receipt['number']+'.pdf');shutil.copyfile(fetched['path'],path)
 return str(path)


def to_ship(job):
 import closing_runtime as c
 if not workspace.complete_volume(job['deal_id']):return
 crm=c.api()
 # A confirmed full transfer proves the production/work stages, not payment.
 # Follow only enabled forward transitions; never mark an advance as received.
 order=['135','136',c.SHIP]
 for _ in range(4):
  deal=crm._call('GET',f"/deal/{job['deal_id']}")['data'];state=str(deal['state']['id'])
  if state in (c.SHIP,c.PAYMENT,c.COMPLETE):return
  floor=order.index(state) if state in order else -1
  choices=[x for x in deal.get('possibleTransitions',[]) if str((x.get('to') or {}).get('id')) in order[floor+1:] and x.get('enabled',True)]
  if not choices:raise ValueError('Объём передан полностью; схема не разрешает переход в Отгрузку из текущей стадии')
  best=max(order.index(str(x['to']['id'])) for x in choices);choices=[x for x in choices if order.index(str(x['to']['id']))==best]
  if len(choices)!=1:raise ValueError('Неоднозначный переход к Отгрузке: требуется проверка схемы')
  transition=choices[0];target=str(transition['to']['id'])
  def move():
   crm._call('POST',f"/deal/{job['deal_id']}/applyTransition",json_body={'contentType':'ProgramTransition','id':transition['id']})
   actual=crm._call('GET',f"/deal/{job['deal_id']}")['data']
   if str(actual['state']['id'])!=target:raise ValueError('Не подтверждён переход в стадию '+target)
   from deal_browser import update_cached_deal
   update_cached_deal(actual)
   return {'ok':True,'state':target}
  c.effect(job,'partial-to-shipment' if target==c.SHIP else 'partial-completed-stage-'+target,move)
 raise ValueError('Не удалось завершить разрешённый маршрут в Отгрузку')


def queue_remainders():
 import closing_runtime as c
 cache=c.CRM/'deal_browser_cache.json'
 if not cache.exists():return
 states={str(d['id']):str((d.get('state') or {}).get('id')) for d in json.loads(cache.read_text())}
 for deal in {s['deal'] for s in workspace.shipments() if s['state']!='legacy_full'}:
  if states.get(deal)!=c.SHIP or workspace.complete_volume(deal):continue
  b=workspace.book(deal)
  if b and b['state']=='error':continue
  if not b or b['state'] not in ('ready','loading') or __import__('time').time()-b['updated']>900:workspace.request(deal);continue
  if b['state']!='ready':continue
  projection=workspace.projection(deal);rows=[{'id':r['id'],'quantity':r['remaining_quantity']} for r in projection['book']['data']['positions'] if Decimal(r['remaining_quantity'])>0]
  try:workspace.confirm({'deal_id':deal,'request_id':'remainder-'+b['data']['fingerprint'],'fingerprint':b['data']['fingerprint'],'transfer_date':c.now().date().isoformat(),'positions':rows},'crm-stage-shipment')
  except ValueError as exc:workspace.save_book(deal,error=str(exc))
