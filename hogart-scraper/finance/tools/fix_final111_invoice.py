import sys,json
sys.path[:0]=['/home/kocher.av/.report-venv/lib/python3.14/site-packages','/home/kocher.av/hogart-scraper/finance']
from post_confirmed import *
a=MegaplanAPI();D=ROOT/'evidence/final111';before=wait_budget(a._call,'GET','/invoice/798')['data'];
if not (D/'invoice_798_before_deal_fix.json').exists():atomic(D/'invoice_798_before_deal_fix.json',before)
original=json.loads((D/'invoice_798_before_deal_fix.json').read_text())
assert before['number']=='05487' and cents(before['sum']['value'])==13009000
if not before.get('deal'):
 auth=wait_budget(v1_auth,a);result=v1_call(a,'/BumsInvoiceApiV01/Invoice/save.api',{'Id':'798','Deal':'851'},auth);atomic(D/'invoice_798_deal_fix_response.json',result)
else:assert before['deal']['id']=='851'
after=wait_budget(a._call,'GET','/invoice/798')['data'];atomic(D/'invoice_798.json',after);assert after['deal']['id']=='851'
for key in ['sum','status','rows','financeOperations']:assert after[key]==original[key],key
for role in ['payer','recipient']:
 for key in ['id','inn','currentAccount']:assert after[role].get(key)==original[role].get(key),(role,key)
 assert after[role]['contractor']['id']==original[role]['contractor']['id']
refs=wait_budget(a._call,'GET','/deal/851/invoices',params={'limit':100})['data'];assert any(str(x['id'])=='798' for x in refs);atomic(D/'deal_851_invoices_after.json',refs)
print('Invoice798 linked to851; amount, status, rows and payments unchanged')
