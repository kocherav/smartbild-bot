import sys,json,collections,datetime
sys.path[:0]=['/home/kocher.av/.report-venv/lib/python3.14/site-packages','/home/kocher.av/hogart-scraper/finance']
from post_confirmed import *
a=MegaplanAPI();auth=wait_budget(v1_auth,a);D=ROOT/'evidence/payment_correction';j=json.loads(JOURNAL.read_text());parts=list(j['operations'].values())
assert len(parts)==37 and all(p.get('payment_semantics')=='cash_only' for p in parts)
items=wait_budget(megaplan_operations,a,auth);atomic(D/'all_final.json',items);before=json.loads((D/'all_before.json').read_text());assert {x['Id'] for x in before}.issubset({x['Id'] for x in items})
byid={str(x['Id']):x for x in items};report=[]
for p in parts:
 o=byid[p['operation_id']];verify_cash_operation(o,p);assert money_match(o,p);assert str(o['DocumentNumber'])==p['document_number'];assert str(o['Deal']['Id'])==p['deal_id'];assert str(o['Contractor']['Id'])==p['contractor_id']
 report.append({'operation_id':p['operation_id'],'deal_id':p['deal_id'],'kind':p['kind'],'cash_cents':p['amount_cents'],'goods_cents':cents(o['SecondarySum']['Value']),'contractor_id':p['contractor_id'],'crm_invoice_id':p.get('crm_invoice_id'),'date':p['date'],'bank_number':p['document_number'],'invoice_number':p['invoice_number']})
invoices=[]
for ident in sorted({p['crm_invoice_id'] for p in parts if p.get('crm_invoice_id')}):
 inv=wait_budget(a._call,'GET','/invoice/'+ident)['data'];want,total=invoice_cash_status(inv);assert inv['status']==want
 expected={p['operation_id'] for p in parts if p.get('crm_invoice_id')==ident};actual={x['id'] for x in inv['financeOperations']};assert expected==actual
 for o in inv['financeOperations']:
  assert cents(o['expenseSum']['value'])==0
 invoices.append({'id':ident,'number':inv['number'],'total_cents':cents(inv['sum']['value']),'paid_cents':total,'status':want,'operation_ids':sorted(actual)})
 atomic(D/('verified_invoice_'+ident+'.json'),inv)
 print('verified invoice',ident,inv['number'],want,total/100,flush=True)
result={'verified_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'operations':report,'invoices':invoices,'remote_before_count':len(before),'remote_after_count':len(items),'new_operation_ids':sorted({str(x['Id']) for x in items}-{str(x['Id']) for x in before}),'supplier_cards_created':sum(x['state']=='created' for x in json.loads((D/'supplier_mapping.json').read_text()).values())}
assert not result['new_operation_ids']
atomic(D/'verified.json',result)
with locked(REG):
 registry=json.loads(REG.read_text());mp={p['operation_id']:p for p in parts}
 for row in registry['operations']:
  if str(row.get('operation_id')) in mp:
   p=mp[str(row['operation_id'])]
   row.update(payment_semantics='cash_only',secondary_cents=0,contractor_id=p['contractor_id'],crm_invoice_id=p.get('crm_invoice_id'))
 atomic(REG,registry)
print('ALL VERIFIED',len(parts),'invoices',len(invoices),'new finance operations',result['new_operation_ids'],flush=True)
