import sys,json,datetime
sys.path[:0]=['/home/kocher.av/.report-venv/lib/python3.14/site-packages','/home/kocher.av/hogart-scraper/finance']
from post_confirmed import *
D=ROOT/'evidence/remaining_oct6';a=MegaplanAPI();auth=wait_budget(v1_auth,a)
items=wait_budget(megaplan_operations,a,auth);atomic(D/'remote_after.json',items)
j=json.loads(JOURNAL.read_text())['operations'];parts=[p for p in j.values() if p.get('allocation_scope')=='company'];assert len(parts)==62 and all(p['state']=='linked' for p in parts)
for p in parts:
 x=select_existing(items,p);assert x and str(x['Id'])==p['operation_id'];verify_cash_operation(x,p);assert money_match(x,p);assert str(x.get('DocumentNumber'))==p['document_number'];assert not x.get('Deal')
 assert str((x.get('Contractor') or {}).get('Id'))==p['contractor_id']
assert len({p['operation_id'] for p in parts})==62
atomic(D/'company_verified.json',dict(verified_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),operations=parts,amount_cents=sum(p['amount_cents'] for p in parts),total_parts=len(j),bank_payments=len({p['bank_operation_id'] for p in j.values()})))
print('Verified',len(parts),'company operations; gross cash',sum(p['amount_cents'] for p in parts)/100,'total bank payments',len({p['bank_operation_id'] for p in j.values()}))
