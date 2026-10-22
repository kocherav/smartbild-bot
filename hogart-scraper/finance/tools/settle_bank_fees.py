import sys,json,datetime
sys.path[:0]=['/home/kocher.av/.report-venv/lib/python3.14/site-packages','/home/kocher.av/hogart-scraper/finance']
from post_confirmed import *
a=MegaplanAPI();auth=wait_budget(v1_auth,a);D=ROOT/'evidence/remaining_oct6';out=[]
with locked(REG):
 j=json.loads(JOURNAL.read_text());atomic(D/'journal_before_fee_settlement.json',j)
 for key,p in j['operations'].items():
  if p.get('category')!='Банковские комиссии' or p.get('allocation_scope')!='company':continue
  assert p['state']=='linked' and p['counterparty_inn']=='7728168971'
  before=v1_call(a,'/BumsFinApiV01/Operation/card.api',{'Id':p['operation_id']},auth)['data']['item'];atomic(D/('fee_before_'+p['operation_id']+'.json'),before)
  assert money_match(before,p) and not before.get('Deal') and str(before['Contractor']['Id'])==p['contractor_id']
  if cents(before['SecondarySum']['Value'])!=p['amount_cents']:
   form=cash_form(p,datetime.datetime.now(datetime.timezone.utc).date().isoformat());form['Id']=p['operation_id'];v1_call(a,'/BumsFinApiV01/Operation/save.api',form,auth)
  after=v1_call(a,'/BumsFinApiV01/Operation/card.api',{'Id':p['operation_id']},auth)['data']['item'];verify_cash_operation(after,p);assert money_match(after,p);assert not after.get('Deal');atomic(D/('fee_after_'+p['operation_id']+'.json'),after)
  p.update(payment_semantics='bank_service_settled',secondary_cents=p['amount_cents']);atomic(JOURNAL,j);out.append(p);print(p['operation_id'],'fee settled',flush=True)
 atomic(D/'fees_settled.json',out)
