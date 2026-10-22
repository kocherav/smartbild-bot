"""Bridge worker for owner-confirmed dashboard shipments."""
import copy, hashlib, json, sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'hogart-scraper/dashboard'))
import shipment_workspace as workspace


def snapshot(deal_id,crm):
 from generate_contract import contract_data
 from payer_signatory_store import get_signatory
 from seller_documents import selected_seller
 from document_tax_policy import require_document_tax,decorate,contract_positions
 from contract_invoice import latest_contract,document_text
 from closing_documents import validate_contract_rows
 deal=crm._call('GET',f'/deal/{deal_id}')['data'];payer=str((deal.get('payer') or {}).get('id') or '')
 if not payer:raise ValueError('В сделке не выбран плательщик')
 deal['payer']=crm._call('GET','/payer/'+payer)['data']
 data=contract_data(deal,{'customer_signatory':get_signatory(payer),'customer_signatory_payer_id':payer})
 if data['missing']:raise ValueError('Заполните реквизиты: '+', '.join(data['missing']))
 seller=selected_seller(str(deal_id))
 if seller['id']!='cliwell':raise ValueError('Для продавца ещё не утверждён шаблон акта')
 selected,path=latest_contract(crm,str(deal_id))
 try:
  text=document_text(path);checked=validate_contract_rows(text,contract_positions(data['positions'],deal_id))
  data['positions']=[{**r,'unit':v['unit']} for r,v in zip(data['positions'],checked)]
  decorate(data,require_document_tax(deal,crm))
  # Ignore CRM stage/time counters; the contract, parties and financial rows matter.
  data.update(seller=seller,contract_file_id=str(selected['id']),contract_sha256=hashlib.sha256(Path(path).read_bytes()).hexdigest(),contract_date_iso=datetime.strptime(data['date'],'%d.%m.%Y').date().isoformat())
  return data
 finally:Path(path).unlink(missing_ok=True)


def validate(job,crm):
 current=snapshot(job['deal_id'],crm)
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
 result.update(positions=rows,total=p['total'],act_number=p['act_number'],partial=True,transfer_dates={'goods':p['transfer_date'],'work':p['transfer_date']},partial_payment=p.get('payment') or {})
 decorate(result)
 return result


def all_edo(job):
 import closing_runtime as c
 ss=workspace.shipments(job['deal_id'])
 if not workspace.complete_volume(job['deal_id']):return False
 jobs=c.registry().read()['jobs']
 return all(jobs.get(s['payload'].get('job_id',s['id']),{}).get('edo_confirmation') and jobs.get(s['payload'].get('job_id',s['id']),{}).get('shipment_finance',{}).get('ok') for s in ss if s['state']!='cancelled')


def invoice(job,crm):
 import closing_runtime as c
 from contract_invoice import payment_offer,create_v1_invoice
 p=job['data'].get('partial_payment') or {}
 if not p:return None
 rates={int(r['tax_rate']) for r in job['data']['positions']}
 if len(rates)!=1:raise ValueError('Для частичного счёта со смешанными ставками нужна разбивка суммы по ставкам')
 rate=next(iter(rates));tax=str(crm.resolve_tax_id('none' if rate==-1 else str(rate)))
 line=f"Частичный расчёт по акту {job['data']['act_number']}, п. {p['clause']} договора. Основание: {p['basis']}"
 def create():
  offer=payment_offer(crm,line,tax)
  inv=create_v1_invoice(crm,{'deal_id':job['deal_id'],'payer_id':job['data']['payer_id'],'basis':line},[{'name':line,'quantity':1,'price':str(p['amount']),'offer_id':offer['id'],'tax_id':tax}])
  return {'ok':True,'invoice_id':str(inv['id']),'number':str(inv['number'])}
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
 crm=c.api();deal=crm._call('GET',f"/deal/{job['deal_id']}")['data']
 if str(deal['state']['id']) in (c.SHIP,c.PAYMENT,c.COMPLETE):return
 choices=[x for x in deal.get('possibleTransitions',[]) if str((x.get('to') or {}).get('id'))==c.SHIP and x.get('enabled',True)]
 if len(choices)!=1:raise ValueError('Объём передан полностью; схема не разрешает переход в Отгрузку из текущей стадии')
 def move():
  crm._call('POST',f"/deal/{job['deal_id']}/applyTransition",json_body={'contentType':'ProgramTransition','id':choices[0]['id']})
  actual=crm._call('GET',f"/deal/{job['deal_id']}")['data']
  if str(actual['state']['id'])!=c.SHIP:raise ValueError('Не подтверждён переход в Отгрузку')
  from deal_browser import update_cached_deal
  update_cached_deal(actual)
  return {'ok':True,'state':c.SHIP}
 c.effect(job,'partial-to-shipment',move)


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
