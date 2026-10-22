import sys,json,datetime
sys.path[:0]=['/home/kocher.av/.report-venv/lib/python3.14/site-packages','/home/kocher.av/hogart-scraper/finance']
from post_confirmed import *
D=ROOT/'evidence/continuation_oct6';path=Path('/home/kocher.av/megaplan-crm/procurement_registry.json');parts=[p for p in json.loads(JOURNAL.read_text())['operations'].values() if p['invoice_number']=='ЭК00-078924'];assert len(parts)==4 and all(p['state']=='linked' for p in parts)
with locked(path):
 data=json.loads(path.read_text());atomic(D/'procurement_before_payment_sync.json',data);inv=next(x for x in data['invoices'] if x['supplier_inn']=='7720298746' and x['number']=='ЭК00-078924');alloc=json.dumps(inv['allocations'],sort_keys=True)
 for p in parts:
  existing=[x for x in inv.get('payments',[]) if str(x.get('megaplan_operation_id'))==p['operation_id'] or x.get('transaction_id')=='bank:'+p['bank_operation_id']]
  if existing:
   assert len(existing)==1 and cents(existing[0]['amount'])==p['amount_cents'];continue
  inv.setdefault('payments',[]).append({'transaction_id':'bank:'+p['bank_operation_id'],'date':p['date'],'amount':p['amount_cents']/100,'megaplan_operation_id':p['operation_id'],'source':'bank_statement','bank_document_number':p['document_number']})
 inv['paid_total']=sum(cents(x['amount']) for x in inv['payments'])/100;assert inv['paid_total']==2400000
 inv['payment_status']='частично оплачен';inv['payment_balance']=round(inv['total']-inv['paid_total'],2)
 assert json.dumps(inv['allocations'],sort_keys=True)==alloc
 atomic(path,data);atomic(D/'elevel_after_payment_sync.json',inv);print('paid_total',inv['paid_total'],'balance',inv['payment_balance'],'allocations unchanged')
