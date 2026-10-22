import sys,json,hashlib,urllib.parse,datetime
sys.path[:0]=['/home/kocher.av/.report-venv/lib/python3.14/site-packages','/home/kocher.av/hogart-scraper/finance']
from post_confirmed import *
import megaplan_transport
D=ROOT/'evidence/deep_review';proof=json.loads((D/'reconciled_failed_attempt.json').read_text());p=proof['attempt'];a=MegaplanAPI();auth=wait_budget(v1_auth,a)
with locked(REG):
 items=wait_budget(megaplan_operations,a,auth);assert not select_existing(items,p)
 form=cash_form(p,p['attempted_at'][:10]);path='/BumsFinApiV01/Operation/save.api';body=urllib.parse.urlencode(form).encode();fp=hashlib.sha256(('POST https://'+a.domain+path).encode()+b'\0'+body).hexdigest()
 with megaplan_transport.connect() as db:
  row=db.execute('SELECT * FROM uncertain WHERE fingerprint=?',(fp,)).fetchone();assert row and row['path']==path
  atomic(D/'resolved_transport_fence.json',{'fingerprint':fp,'bank_operation_id':p['bank_operation_id'],'absence_checks':3,'proof':'reconciled_failed_attempt.json','resolved_at':datetime.datetime.now(datetime.timezone.utc).isoformat()})
  db.execute('DELETE FROM uncertain WHERE fingerprint=?',(fp,));db.commit()
 print('Exact reconciled request fence resolved; global protections unchanged')
