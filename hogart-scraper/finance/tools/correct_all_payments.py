import sys,json,re,collections
sys.path[:0]=['/home/kocher.av/.report-venv/lib/python3.14/site-packages','/home/kocher.av/hogart-scraper/finance']
from post_confirmed import *
a=MegaplanAPI();auth=wait_budget(v1_auth,a);D=ROOT/'evidence/payment_correction'
j=json.loads(JOURNAL.read_text());parts=list(j['operations'].values());snapshot={str(x['Id']):x for x in json.loads((D/'all_before.json').read_text())}
# All target operations originate from bank payments, without a receipt/shipment event.
# Their old secondary sums were implicit API defaults, not documentary evidence.
mapping={}
for p in parts:
 if p['kind']=='income':
  match=re.search(r'invoice_(\d+)\.json',p['evidence']);ident=match.group(1) if match else '798'
  file=D/('invoice_live_'+ident+'.json')
  if not file.exists():atomic(file,wait_budget(a._call,'GET','/invoice/'+ident))
  inv=json.loads(file.read_text())['data'];assert inv['payer']['inn']==p['counterparty_inn'];assert inv['recipient']['currentAccount'].endswith('1580' if p['account_id']=='22' else '1572');assert inv['payer']['contractor']['id']
  mapping[p['operation_id']]=inv
# Validate whole-invoice totals before any updates.
byinvoice=collections.defaultdict(list)
for p in parts:
 if p['operation_id'] in mapping:byinvoice[mapping[p['operation_id']]['id']].append(p)
for ident,pp in byinvoice.items():
 inv=mapping[pp[0]['operation_id']];assert sum(p['amount_cents'] for p in pp)<=cents(inv['sum']['value'])
atomic(D/'invoice_mapping.json',{k:{'id':v['id'],'number':v['number'],'contractor_id':v['payer']['contractor']['id'],'total_cents':cents(v['sum']['value'])} for k,v in mapping.items()})
with locked(REG):
 for p in parts:
  if p['kind']=='expense':continue
  if p.get('payment_semantics')=='cash_only':continue
  ident=p['operation_id'];before=v1_call(a,'/BumsFinApiV01/Operation/card.api',{'Id':ident},auth)['data']['item'];assert money_match(before,p);assert before.get('Deal',{}).get('Id')==int(p['deal_id']);atomic(D/('before_'+ident+'.json'),before)
  form={'Id':ident,'Model[SecondarySum][Value]':'0.00','Model[SecondarySum][Currency]':'1','Model[ControlDate]':'2026-10-06'}
  inv=mapping.get(ident)
  if inv:form.update({'Model[Invoice]':inv['id'],'Model[Contractor]':inv['payer']['contractor']['id']})
  response=v1_call(a,'/BumsFinApiV01/Operation/save.api',form,auth);atomic(D/('save_'+ident+'.json'),response)
  after=v1_call(a,'/BumsFinApiV01/Operation/card.api',{'Id':ident},auth)['data']['item'];atomic(D/('after_'+ident+'.json'),after)
  assert money_match(after,p) and after['DocumentNumber']==p['document_number'];assert cents(after['SecondarySum']['Value'])==0;assert after.get('Deal',{}).get('Id')==int(p['deal_id'])
  p.update(secondary_cents=0,payment_semantics='cash_only',control_date='2026-10-06',control_date_basis='Internal audit review date; not promised shipment date')
  if inv:p.update(crm_invoice_id=inv['id'],contractor_id=inv['payer']['contractor']['id'])
  j['operations'][p['key']]=p;atomic(JOURNAL,j);print('corrected',ident,p['kind'],p['amount_cents']/100,'invoice',inv['number'] if inv else '-',flush=True)
 # API associates payment with invoice but may mark any partial payment as fully paid.
 for ident,pp in byinvoice.items():
  inv=wait_budget(a._call,'GET','/invoice/'+ident)['data'];atomic(D/('linked_invoice_'+ident+'.json'),inv)
  expected={p['operation_id'] for p in pp};actual={x['id'] for x in inv.get('financeOperations',[])};assert expected.issubset(actual)
  total=sum(cents(x.get('incomeSum',x.get('sum',{})).get('value',0)) for x in inv['financeOperations'] if x['kind']=='income')
  if actual!=expected:raise ValueError('Unexpected other invoice operations; review total before status change')
  paid=total>=cents(inv['sum']['value']);want='paid' if paid else 'drawn'
  if inv['status']!=want:
   v1_call(a,'/BumsInvoiceApiV01/Invoice/save.api',{'Id':ident,'Model[Status]':'3' if paid else '2'},auth)
  final=wait_budget(a._call,'GET','/invoice/'+ident)['data'];atomic(D/('final_invoice_'+ident+'.json'),final)
  assert final['status']==want and expected.issubset({x['id'] for x in final.get('financeOperations',[])})
  print('invoice',ident,final['number'],'paid',total/100,'total',final['sum']['value'],'status',want,flush=True)
 print('DONE',len(parts),len(byinvoice),flush=True)
