import sys,json,datetime
sys.path[:0]=['/home/kocher.av/.report-venv/lib/python3.14/site-packages','/home/kocher.av/hogart-scraper/finance']
from post_confirmed import *
a=MegaplanAPI();auth=wait_budget(v1_auth,a);D=ROOT/'evidence/last_six_20261007';allocations=json.loads((D/'reviewed_allocations.json').read_text());company=json.loads((D/'company_plan.json').read_text());ids=set(allocations)|{p['bank_operation_id'] for p in company};j=json.loads(JOURNAL.read_text())['operations'];parts=[p for p in j.values() if p['bank_operation_id'] in ids];assert len(parts)==sum(len(x['allocations']) for x in allocations.values())+len(company) and all(p['state']=='linked' for p in parts);verified=[]
for p in parts:
 x=v1_call(a,'/BumsFinApiV01/Operation/card.api',{'Id':p['operation_id']},auth)['data']['item'];verify_cash_operation(x,p);assert money_match(x,p);assert (str((x.get('Deal') or {}).get('Id') or '')==p['deal_id']);assert str(x['OperationType']['Id'])==p['operation_type'];assert str(x['Contractor']['Id'])==p['contractor_id'];assert x['DocumentNumber']==p['document_number'];atomic(D/('verified_operation_'+p['operation_id']+'.json'),x);verified.append(p);print('verified',p['operation_id'],p['amount_cents']/100,flush=True)
atomic(D/'verified.json',{'errors':[],'verified_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'operations':verified,'new_cash_cents':sum(p['amount_cents'] for p in verified),'total_crm_parts':len(j),'bank_payments':len({p['bank_operation_id'] for p in j.values()})})

with locked(REG):
 registry=json.loads(REG.read_text())
 for p in parts:
  hits=[r for r in registry['operations'] if str(r.get('operation_id'))==p['operation_id']];assert len(hits)==1
  hits[0].update(payment_semantics='cash_only',secondary_cents=0,contractor_id=p['contractor_id'],verification_source='finance/evidence/last_six_20261007/verified.json')
 atomic(REG,registry)
