import sys,json,re
from decimal import Decimal,ROUND_HALF_UP
sys.path[:0]=['/home/kocher.av/.report-venv/lib/python3.14/site-packages','/home/kocher.av/hogart-scraper/finance']
from post_confirmed import *
D=ROOT/'evidence/final111';audit=json.loads((D/'audit.json').read_text());assert len(audit['operations'])==111 and not audit['errors'];parts=audit['operations']
with locked(REG):
 registry=json.loads(REG.read_text());atomic(D/'finance_registry_before.json',registry);updates=[]
 for p in parts:
  matches=[x for x in registry['operations'] if str(x.get('operation_id'))==p['operation_id']];assert len(matches)==1
  x=matches[0];assert cents(x['amount'])==p['amount_cents']
  x.update(payment_semantics=p['payment_semantics'],secondary_cents=expected_secondary_cents(p),contractor_id=p['contractor_id'],crm_invoice_id=p.get('crm_invoice_id'),verification_source='finance/evidence/final111/audit.json')
 atomic(REG,registry)
path=Path('/home/kocher.av/megaplan-crm/procurement_registry.json')
with locked(path):
 data=json.loads(path.read_text());atomic(D/'procurement_before.json',data);report=[]
 for inv in data['invoices']:
  matches=[p for p in parts if p['kind']=='expense' and p.get('deal_id') and p['counterparty_inn']==inv.get('supplier_inn') and p['invoice_number']==inv['number']]
  if not matches:continue
  preserved=json.dumps({k:inv.get(k) for k in ['allocations','total','plan_total_rub','items']},sort_keys=True);new=[]
  for p in matches:
   old=[x for x in inv.get('payments',[]) if str(x.get('megaplan_operation_id'))==p['operation_id'] or x.get('transaction_id')=='bank:'+p['bank_operation_id']]
   if old:assert len(old)==1 and cents(old[0]['amount'])==p['amount_cents'];continue
   inv.setdefault('payments',[]).append({'transaction_id':'bank:'+p['bank_operation_id'],'date':p['date'],'amount':p['amount_cents']/100,'megaplan_operation_id':p['operation_id'],'source':'bank_statement','bank_document_number':p['document_number']});new.append(p['operation_id'])
  paid=sum(cents(x['amount']) for x in inv['payments']);inv['paid_total']=paid/100;settlement=cents(inv['total'])
  if inv.get('currency') not in [None,'RUB','RUR']:
   assert inv['number']=='DAER-023701' and len(matches)==1
   rate=Decimal('84.5863');amount=(Decimal(str(inv['foreign_total']))*rate).quantize(Decimal('.01'),rounding=ROUND_HALF_UP);assert cents(amount)==paid
   inv.update(settlement_total_rub=float(amount),settlement_rate=float(rate),settlement_rate_date=matches[0]['date'],settlement_rate_source='Курс84,5863 в назначении банковского платежа №64; счёт требует курс на день оплаты',payment_plan_difference=round(float(amount)-inv['total'],2));settlement=cents(amount)
  inv['payment_balance']=(settlement-paid)/100;inv['payment_status']='оплачен' if paid==settlement else 'частично оплачен' if paid<settlement else 'переплата — сверить'
  assert json.dumps({k:inv.get(k) for k in ['allocations','total','plan_total_rub','items']},sort_keys=True)==preserved
  report.append({'invoice':inv['number'],'added_operation_ids':new,'paid_total':inv['paid_total'],'payment_balance':inv['payment_balance'],'status':inv['payment_status'],'plan_difference':inv.get('payment_plan_difference',0)})
 atomic(path,data);atomic(D/'registry_sync.json',report)
print('finance records synchronized',len(parts),'supplier invoices',len(report),'added payment links',sum(len(x['added_operation_ids']) for x in report))
