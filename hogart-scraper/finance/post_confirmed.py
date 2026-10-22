"""Post reviewed bank payments, with a durable journal and native deal links."""
import sys,json,os,fcntl,tempfile,datetime,time
from decimal import Decimal
from payment_semantics import cash_form, invoice_cash_status, verify_cash_operation, verified_company_operation, expected_secondary_cents, semantics_label
from pathlib import Path
sys.path.insert(0,'/home/kocher.av/megaplan-crm')
from megaplan_api import MegaplanAPI
from contract_invoice import v1_auth, v1_call as raw_v1_call
from megaplan_transport import ProtectionPause
from megaplan_finance import megaplan_operations
from registry_transaction import locked
def wait_budget(fn,*args,**kwargs):
 for attempt in range(31):
  try:return fn(*args,**kwargs)
  except ProtectionPause as exc:
   if not any(t in str(exc) for t in ('бюджет запросов','очередь запросов занята','защитная пауза')) or attempt==30:raise
   print('CRM budget pause; retrying an unsent request in30 seconds',flush=True);time.sleep(30)
def v1_call(*a,**kw):return wait_budget(raw_v1_call,*a,**kw)
ROOT=Path(__file__).resolve().parent
REG=Path('/home/kocher.av/megaplan-crm/megaplan_finance_registry.json')
JOURNAL=ROOT/'data/posting_journal.json'

def atomic(path,data):
 old=path.stat() if path.exists() else None
 fd,tmp=tempfile.mkstemp(dir=path.parent,prefix='.posting-')
 try:
  with os.fdopen(fd,'w') as f:
   json.dump(data,f,ensure_ascii=False,indent=2);f.flush();os.fsync(f.fileno())
  os.chmod(tmp,old.st_mode&0o777 if old else 0o600)
  if os.geteuid()==0:os.chown(tmp,old.st_uid if old else 1001,old.st_gid if old else 27)
  os.replace(tmp,path)
 finally:
  if os.path.exists(tmp):os.unlink(tmp)

def cents(x):return int((Decimal(str(x))*100).quantize(Decimal('1')))
def money_match(o,p):
 return (str((o.get('RealAccount') or {}).get('Id'))==p['account_id'] and o.get('Date','')[:10]==p['date'] and o.get('Kind')==p['kind'] and cents(o['Sum']['Value'])==p['amount_cents'])
def select_existing(items,p):
 marked=[o for o in items if p['marker'] in o.get('Description','')]
 if marked:
  if len(marked)!=1 or not money_match(marked[0],p):raise ValueError('Marker conflict')
  return marked[0]
 # Other explicitly planned portions of this bank movement are not duplicates of this portion.
 sibling_markers=set(p.get('sibling_markers',[]))-{p['marker']}
 same=[o for o in items if money_match(o,p) and not (str(o.get('DocumentNumber') or '')==p['document_number'] and any('['+m+']' in o.get('Description','') for m in sibling_markers))]
 # An identical amount/account/date is held even if an old entry omitted bank number.
 if same:
  exact=[o for o in same if str(o.get('DocumentNumber') or '')==p['document_number']]
  if len(same)==len(exact)==1:return exact[0]
  if p.get('allocation_scope')=='company' and all(str(o.get('DocumentNumber') or '').strip() for o in same):
   if len(exact)==1:return exact[0]
   if not exact:return None
  raise ValueError('Ambiguous pre-existing payment')
 return None

def main():
 if (ROOT/'data/posting_paused.json').exists():raise RuntimeError('Autoposting paused for payment semantics audit')
 plan=json.loads((ROOT/'evidence/posting/plan.json').read_text());api=MegaplanAPI();auth=wait_budget(v1_auth,api)
 with locked(REG):
  items=wait_budget(megaplan_operations,api,auth);atomic(ROOT/'evidence/posting/remote_before_commit.json',items)
  journal=json.loads(JOURNAL.read_text()) if JOURNAL.exists() else {'operations':{}}
  registry=json.loads(REG.read_text())
  # Full preflight before any new payment: no partially covered bank movement is retried.
  by_bank={}
  for p in plan:by_bank.setdefault(p['bank_operation_id'],[]).append(p)
  for parts in by_bank.values():
   p=parts[0]
   group=[o for o in items if str((o.get('RealAccount') or {}).get('Id'))==p['account_id'] and o.get('Date','')[:10]==p['date'] and o.get('Kind')==p['kind'] and str(o.get('DocumentNumber') or '')==p['document_number']]
   known_ids={str(v['operation_id']) for v in journal['operations'].values() if v.get('bank_operation_id')==p['bank_operation_id'] and v.get('operation_id')}
   if group and sum(cents(o['Sum']['Value']) for o in group)!=sum(x['amount_cents'] for x in parts) and not {str(o['Id']) for o in group}.issubset(known_ids):raise ValueError('Unexplained partial bank movement already exists')
   for x in parts:
    existing=select_existing(items,x)
    if existing and x.get('allocation_scope')=='company':
     verify_cash_operation(existing,x)
     if str((existing.get('Contractor') or {}).get('Id'))!=x['contractor_id'] or existing.get('Deal'):raise ValueError('Company expense has wrong contractor/deal')
  for p in plan:
   if not p.get('deal_id') and not verified_company_operation(p):raise ValueError('Unapproved company-level payment')
   if journal['operations'].get(p['key'],{}).get('state')!='linked':cash_form(p,datetime.datetime.now(datetime.timezone.utc).date().isoformat())
   if p['kind']=='income' and p.get('crm_invoice_id') and journal['operations'].get(p['key'],{}).get('state')!='linked':
    cash_form(p,datetime.datetime.now(datetime.timezone.utc).date().isoformat())
    inv=wait_budget(api._call,'GET','/invoice/'+p['crm_invoice_id'])['data']
    if inv['payer'].get('inn')!=p['counterparty_inn'] or inv['payer'].get('contractor',{}).get('id')!=p['contractor_id']:raise ValueError('Invoice payer mismatch')
    if inv['recipient'].get('currentAccount')!= {'20':'40702810402570001572','22':'40702810902570001580'}[p['account_id']]:raise ValueError('Invoice recipient account mismatch')
    _,paid=invoice_cash_status(inv)
    if not select_existing(items,p):
     unpaid_planned=sum(x['amount_cents'] for x in plan if x.get('crm_invoice_id')==inv['id'] and not select_existing(items,x))
     if paid+unpaid_planned>cents(inv['sum']['value']):raise ValueError('Payment exceeds invoice remainder')
  created=recovered=0
  for p in plan:
   old=journal['operations'].get(p['key'],{})
   existing=select_existing(items,p)
   if old.get('operation_id') and (not existing or str(existing['Id'])!=old['operation_id']):raise ValueError('Journal and remote history disagree')
   if old.get('state')=='linked' and existing:
    recovered+=1;continue
   if old.get('state')=='creating' and not existing:raise ValueError('Uncertain previous create: manual remote verification required')
   if existing:
    ident=str(existing['Id']);recovered+=1
   else:
    journal['operations'][p['key']]={**p,'state':'creating','attempted_at':datetime.datetime.now(datetime.timezone.utc).isoformat()};atomic(JOURNAL,journal)
    form=cash_form(p,datetime.datetime.now(datetime.timezone.utc).date().isoformat())
    response=v1_call(api,'/BumsFinApiV01/Operation/save.api',form,auth);item=response['data'].get('item') or response['data'].get('Operation') or response['data'];ident=str(item.get('Id') or item.get('id') or '')
    if not ident:raise ValueError('Missing operation ID')
    journal['operations'][p['key']]={**p,'operation_id':ident,'state':'created'};atomic(JOURNAL,journal)
    item=v1_call(api,'/BumsFinApiV01/Operation/card.api',{'Id':ident},auth)['data']['item']
    if not money_match(item,p) or str(item.get('DocumentNumber'))!=p['document_number']:raise ValueError('Created payment differs from plan')
    verify_cash_operation(item,p)
    if p.get('allocation_scope')=='company' and (str((item.get('Contractor') or {}).get('Id'))!=p['contractor_id'] or item.get('Deal')):raise ValueError('Unexpected company expense contractor/deal')
    items.append(item);created+=1
   if verified_company_operation(p) and p['operation_type']=='32':
    native=wait_budget(api._call,'GET','/finOperation/'+ident)['data']
    if native.get('type',{}).get('id')!='32' or native.get('status')!='closed' or native.get('invoices'):raise ValueError('Unexpected nontrade income semantics')
    if cents(native['incomeSum']['value'])!=p['amount_cents'] or cents((native.get('expenseSum') or {}).get('value',0))!=0:raise ValueError('Nontrade income has unexpected second side')
    atomic(ROOT/'evidence/remaining_oct6'/('verified_nontrade_'+ident+'.json'),native)
   journal['operations'][p['key']]={**p,'operation_id':ident,'state':'verified'};atomic(JOURNAL,journal)
   if p.get('deal_id'):
    linked=wait_budget(api._call,'POST',f'/finOperation/{ident}/linkWith',json_body={'contentType':'Deal','id':p['deal_id']})['data']
    if str(linked.get('id'))!=p['deal_id']:raise ValueError('Wrong linked deal')
    if not any(str(o.get('id'))==ident for o in linked.get('financeOperations',[])):
     # The returned collection can be truncated; retain created ID but do not claim a verified link.
     raise ValueError('Native deal link not visible in API response')
   if p.get('crm_invoice_id'):
    op=wait_budget(api._call,'GET','/finOperation/'+ident)['data']
    if p['crm_invoice_id'] not in {x['id'] for x in op.get('invoices',[])}:raise ValueError('Invoice not linked to operation')
    inv=wait_budget(api._call,'GET','/invoice/'+p['crm_invoice_id'])['data']
    if ident not in {x['id'] for x in inv.get('financeOperations',[])}:raise ValueError('Operation not linked to invoice')
    wanted,paid=invoice_cash_status(inv)
    if inv['status']!=wanted:v1_call(api,'/BumsInvoiceApiV01/Invoice/save.api',{'Id':inv['id'],'Model[Status]':'3' if wanted=='paid' else '2'},auth)
    inv=wait_budget(api._call,'GET','/invoice/'+p['crm_invoice_id'])['data']
    if inv['status']!=wanted:raise ValueError('Wrong invoice payment status')
   journal['operations'][p['key']].update(state='linked',payment_semantics=semantics_label(p),secondary_cents=expected_secondary_cents(p));atomic(JOURNAL,journal)
   if not any(str(o.get('operation_id'))==ident for o in registry['operations']):
    registry['operations'].append({'id':p['key'],'candidate_id':'statement:'+p['bank_operation_id'],'operation_id':ident,'invoice_number':p['invoice_number'],'amount':p['amount_cents']/100,'deal_ids':[p['deal_id']] if p.get('deal_id') else [],'source':'bank_statement','bank_operation_id':p['bank_operation_id'],'bank_date':p['date'],'bank_document_number':p['document_number'],'account_id':p['account_id'],'counterparty_inn':p['counterparty_inn'],'kind':p['kind'],'created_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'recovered':bool(existing)})
    atomic(REG,registry)
   print(p['key'],ident,p['deal_id'],p['amount_cents']/100,'linked',flush=True)
  print(json.dumps({'created':created,'reused':recovered,'linked':len(plan)},ensure_ascii=False),flush=True)
if __name__=='__main__':main()
