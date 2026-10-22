import sys,json
sys.path[:0]=['/home/kocher.av/.report-venv/lib/python3.14/site-packages','/home/kocher.av/hogart-scraper/finance']
from post_confirmed import *
D=ROOT/'evidence/finish_all';a=json.loads((D/'audit.json').read_text());assert len(a['operations'])==219 and not a['errors']
with locked(REG):
 r=json.loads(REG.read_text());atomic(D/'finance_registry_before_sync.json',r)
 for p in a['operations']:
  matches=[x for x in r['operations'] if str(x.get('operation_id'))==p['operation_id']];assert len(matches)==1;x=matches[0];assert cents(x['amount'])==p['amount_cents']
  x.update(payment_semantics=p['payment_semantics'],secondary_cents=expected_secondary_cents(p),contractor_id=p['contractor_id'],crm_invoice_id=p.get('crm_invoice_id'),allocation_scope=p.get('allocation_scope','deal'),verification_source='finance/evidence/finish_all/audit.json')
 atomic(REG,r)
print('Synchronized',len(a['operations']))
