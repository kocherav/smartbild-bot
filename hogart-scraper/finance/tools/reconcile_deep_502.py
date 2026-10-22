import sys,datetime
sys.path[:0]=['/home/kocher.av/.report-venv/lib/python3.14/site-packages','/home/kocher.av/hogart-scraper/finance']
from post_confirmed import *
a=MegaplanAPI();auth=wait_budget(v1_auth,a);D=ROOT/'evidence/deep_review'
with locked(REG):
 items=wait_budget(megaplan_operations,a,auth);atomic(D/'remote_after_502.json',items);j=json.loads(JOURNAL.read_text());uncertain=[p for p in j['operations'].values() if p['state']=='creating'];assert len(uncertain)==1;p=uncertain[0];assert p['deal_id']=='883' and not p.get('operation_id')
 assert not select_existing(items,p)
 assert not [o for o in items if str((o.get('RealAccount') or {}).get('Id'))==p['account_id'] and o.get('Date','')[:10]==p['date'] and str(o.get('DocumentNumber') or '')==p['document_number']]
 previous=json.loads((ROOT/'evidence/posting/remote_before_commit.json').read_text());assert not select_existing(previous,p)
 atomic(D/'reconciled_failed_attempt.json',{'attempt':p,'verified_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'result':'После502 два полных независимых чтения историиCRM не обнаружили ни маркер, ни платёж по номеру/дате/счёту; создание не произошло. Разрешён один повтор с тем же ключом.'})
 p.update(state='retry_after_verified_absence',recovery_source='finance/evidence/deep_review/reconciled_failed_attempt.json');atomic(JOURNAL,j);print('uncertain request reconciled: absent remotely')
