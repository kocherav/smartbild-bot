"""Save evidenced links to existing bank registry, preserving prior assignments."""
import datetime,fcntl,json,os,shutil
from pathlib import Path
from decimal import Decimal
from ledger import ROOT,connect,records
TARGET=Path('/home/kocher.av/megaplan-crm/bank_statement_registry.json')
def main():
 rows=records(connect(ROOT/'data/ledger.sqlite'),json.loads((ROOT/'accounts.json').read_text()))
 with open(str(TARGET)+'.lock','a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX)
  registry=json.loads(TARGET.read_text());updates=[]
  for r in rows:
   if not r.get('verified_deal_id'):continue
   matches=[t for t in registry['transactions'] if t.get('account')==r['account'] and t.get('date')=='.'.join(reversed(r['date'].split('-'))) and str(t.get('document_number'))==r['number'] and str(t.get('counterparty_inn'))==r['inn'] and Decimal(str(t['amount']))*100==r['amount_cents'] and t.get('direction')==('income' if r['direction']=='in' else 'expense')]
   if len(matches)!=1:raise ValueError('Nonunique registry match')
   t=matches[0]
   if t.get('status')=='assigned':
    if str(t.get('deal_id'))!=r['verified_deal_id']:raise ValueError('Conflicting assignment')
    continue
   t.update(status='assigned',deal_id=r['verified_deal_id'],assigned_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),assignment_source='document_research',assignment_evidence=r['crm_evidence'],source_operation_id=r['id'])
   updates.append({'registry_id':t['id'],'operation_id':r['id'],'deal_id':r['verified_deal_id'],'evidence':r['crm_evidence']})
  if updates:
   stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%f')
   backup=ROOT/'data'/('bank_registry_before_links_'+stamp+'.json');shutil.copy2(TARGET,backup)
   audit=ROOT/'data'/('link_audit_'+stamp+'.json');audit.write_text(json.dumps(updates,ensure_ascii=False,indent=2))
   temporary=TARGET.with_suffix('.research.tmp');temporary.write_text(json.dumps(registry,ensure_ascii=False,indent=2));os.chmod(temporary,TARGET.stat().st_mode & 0o777);temporary.replace(TARGET)
  print(json.dumps({'new_verified_assignments':len(updates),'remote_crm_payments_created':0}))
if __name__=='__main__':main()
