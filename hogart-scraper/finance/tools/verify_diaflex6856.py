import sys,json,datetime
sys.path[:0]=['/home/kocher.av/.report-venv/lib/python3.14/site-packages','/home/kocher.av/hogart-scraper/finance']
from post_confirmed import *
D=ROOT/'evidence/diaflex6856';x=json.loads((D/'confirmation.json').read_text());j=json.loads(JOURNAL.read_text())['operations'];parts=[p for p in j.values() if p['bank_operation_id']==x['bank_operation_id']];assert len(parts)==2 and all(p['state']=='linked' for p in parts);assert len({p['operation_id'] for p in parts})==2;assert sum(p['amount_cents'] for p in parts)==1638300;assert {p['deal_id'] for p in parts}=={'858','862'}
a=MegaplanAPI();auth=wait_budget(v1_auth,a)
for p in parts:
 o=v1_call(a,'/BumsFinApiV01/Operation/card.api',{'Id':p['operation_id']},auth)['data']['item'];verify_cash_operation(o,p);assert money_match(o,p) and p['marker'] in o['Description'];assert str(o['Deal']['Id'])==p['deal_id'] and str(o['Contractor']['Id'])==p['contractor_id'] and str(o['DocumentNumber'])=='112';atomic(D/('operation_'+p['operation_id']+'.json'),o)
items=wait_budget(megaplan_operations,a,auth);matching=[o for o in items if money_match(o,parts[0]) and str(o.get('DocumentNumber'))=='112'];assert {str(o['Id']) for o in matching}=={p['operation_id'] for p in parts}
atomic(D/'verified.json',{'checked_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'operations':parts,'errors':[]});print('Verified distinct cash-only parts',[(p['operation_id'],p['deal_id'],p['amount_cents']) for p in parts],flush=True)
with locked(REG):
 registry=json.loads(REG.read_text())
 for p in parts:
  hits=[r for r in registry['operations'] if str(r.get('operation_id'))==p['operation_id']];assert len(hits)==1
  hits[0].update(payment_semantics='cash_only',secondary_cents=0,contractor_id=p['contractor_id'],allocation_scope='deal',verification_source='finance/evidence/diaflex6856/verified.json')
 atomic(REG,registry)
