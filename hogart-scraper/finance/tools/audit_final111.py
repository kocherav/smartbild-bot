import sys,json,datetime,collections
sys.path[:0]=['/home/kocher.av/.report-venv/lib/python3.14/site-packages','/home/kocher.av/hogart-scraper/finance']
from post_confirmed import *
D=ROOT/'evidence/final111';a=MegaplanAPI();auth=wait_budget(v1_auth,a)
j=json.loads(JOURNAL.read_text());atomic(D/'journal_before.json',j);parts=list(j['operations'].values());assert len(parts)==111
items=wait_budget(megaplan_operations,a,auth);atomic(D/'remote.json',items)
rows={r['id']:r for r in json.loads((ROOT/'reports/ledger.json').read_text())};errors=[];checked=[]
def check(condition,message):
 if not condition:raise ValueError(message)
for p in parts:
 try:
  check(p['state']=='linked','journal state');o=select_existing(items,p);check(o is not None and str(o['Id'])==p['operation_id'],'remote id');verify_cash_operation(o,p)
  check(money_match(o,p),'cash/date/account');check(str(o.get('DocumentNumber'))==p['document_number'],'bank number');check(str((o.get('Contractor') or {}).get('Id'))==p['contractor_id'],'contractor');check(str((o.get('OperationType') or {}).get('Id'))==p['operation_type'],'operation type')
  check(str((o.get('Deal') or {}).get('Id') or '')==p.get('deal_id',''),'deal')
  r=rows[p['bank_operation_id']];check(r['date']==p['date'] and r['number']==p['document_number'] and r['inn']==p['counterparty_inn'],'bank identity')
  group=[q for q in parts if q['bank_operation_id']==p['bank_operation_id']];check(sum(q['amount_cents'] for q in group)==r['amount_cents'],'bank allocation sum')
  dup=[x for x in items if money_match(x,p) and str(x.get('DocumentNumber') or '')==p['document_number']];check(len(dup)==1,'duplicate bank amount/date/document')
  n=wait_budget(a._call,'GET','/finOperation/'+p['operation_id'])['data'];atomic(D/('native_'+p['operation_id']+'.json'),n)
  if p.get('crm_invoice_id'):check(p['crm_invoice_id'] in {str(x['id']) for x in n.get('invoices',[])},'native invoice link')
  if p.get('payment_semantics')=='nontrade_income':check(cents(n['incomeSum']['value'])==p['amount_cents'] and cents((n.get('expenseSum') or {}).get('value',0))==0 and not n.get('invoices') and n['status']=='closed','nontrade semantics')
  checked.append(p);print('OK',p['operation_id'],flush=True)
 except Exception as e:errors.append({'operation_id':p['operation_id'],'error':str(e)});print('ERROR',p['operation_id'],str(e),flush=True)
invoices=[]
for iid in sorted({p['crm_invoice_id'] for p in parts if p.get('crm_invoice_id')}):
 try:
  inv=wait_budget(a._call,'GET','/invoice/'+iid)['data'];atomic(D/('invoice_'+iid+'.json'),inv);wanted,paid=invoice_cash_status(inv);check(inv['status']==wanted,'invoice status');expected={p['operation_id'] for p in parts if p.get('crm_invoice_id')==iid};check(expected.issubset({str(o['id']) for o in inv['financeOperations']}),'invoice reverse link');invoices.append({'id':iid,'number':inv['number'],'status':wanted,'paid_cents':paid,'total_cents':cents(inv['sum']['value'])})
 except Exception as e:errors.append({'invoice_id':iid,'error':str(e)})
check(len({p['operation_id'] for p in parts})==111,'duplicate journal id')
atomic(D/'audit.json',{'checked_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'operations':checked,'invoices':invoices,'errors':errors,'bank_payments':len({p['bank_operation_id'] for p in parts})})
print('DONE',len(checked),'invoices',len(invoices),'errors',errors,flush=True)
