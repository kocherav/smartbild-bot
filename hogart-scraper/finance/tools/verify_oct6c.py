import sys,json,datetime
sys.path[:0]=['/home/kocher.av/.report-venv/lib/python3.14/site-packages','/home/kocher.av/hogart-scraper/finance']
from post_confirmed import *
a=MegaplanAPI();auth=wait_budget(v1_auth,a);D=ROOT/'evidence/continuation_oct6c';links=json.loads((D/'new_links.json').read_text());ids={x['operation_id'] for x in links};j=json.loads(JOURNAL.read_text())['operations'];parts=[p for p in j.values() if p['bank_operation_id'] in ids];assert len(parts)==1;verified=[]
for p in parts:
 x=v1_call(a,'/BumsFinApiV01/Operation/card.api',{'Id':p['operation_id']},auth)['data']['item'];verify_cash_operation(x,p);assert money_match(x,p);assert str(x['Deal']['Id'])==p['deal_id'];assert str(x['Contractor']['Id'])==p['contractor_id'];assert x['DocumentNumber']==p['document_number'];atomic(D/('verified_operation_'+p['operation_id']+'.json'),x);verified.append(p);print('verified',p['operation_id'],p['amount_cents']/100,flush=True)
atomic(D/'verified.json',{'verified_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'operations':verified,'new_cash_cents':sum(p['amount_cents'] for p in verified),'total_crm_parts':len(j),'bank_payments':len({p['bank_operation_id'] for p in j.values()})})
