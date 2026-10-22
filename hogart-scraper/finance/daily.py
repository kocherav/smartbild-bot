#!/usr/bin/env python3
"""Read-only IMAP intake + atomic local import. Never sends or deletes mail."""
import datetime as dt, email, email.policy, fcntl, hashlib, imaplib, json, os, shutil, ssl, subprocess, sys
from email.utils import getaddresses
from pathlib import Path
from zoneinfo import ZoneInfo
from ledger import ROOT, connect, import_zip

from mail_intake import retrieve

def health(db):
    today=dt.datetime.now(ZoneInfo('Europe/Moscow')).date(); yesterday=today-dt.timedelta(days=1)
    result=[]
    for account,owner in json.loads((ROOT/'accounts.json').read_text()).items():
        bounds=[]
        for start,end,meta in db.execute('SELECT start,end,metadata FROM statements WHERE account=?',(account,)):
            h=json.loads(meta)['header']; creation=dt.datetime.strptime(h['ДатаСоздания'],'%d.%m.%Y').date()
            # Intraday snapshot never certifies its creation date as complete.
            bounds.append((dt.date.fromisoformat(start), min(dt.date.fromisoformat(end),creation-dt.timedelta(days=1))))
        complete=max((end for start,end in bounds if end>=start),default=None)
        merged=[]
        for start,end in sorted(bounds):
            if end<start:continue
            if merged and start<=merged[-1][1]+dt.timedelta(days=1):merged[-1]=(merged[-1][0],max(end,merged[-1][1]))
            else:merged.append((start,end))
        result.append({'account':account,'company':owner['name'],'complete_through':str(complete) if complete else None,'needs_statement':complete is None or complete<yesterday,'internal_gaps':len(merged)>1,'owner_confirmed':bool(owner['inn'])})
    return result

def main():
    os.umask(0o077)
    for folder in ['inbox','archive','quarantine','reports','data']: (ROOT/folder).mkdir(exist_ok=True)
    with (ROOT/'data/run.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        errors=[];results=[];mail_ok=False;report_result=None
        if '--local-only' not in sys.argv:
            try:
                notices=retrieve();mail_ok=True
                errors.extend({'stage':'intake_review',**x} for x in notices)
            except Exception as e:errors.append({'stage':'mail','error':type(e).__name__+': '+str(e)})
        db=connect(ROOT/'data/ledger.sqlite')
        backup=connect(ROOT/'data/ledger.backup.sqlite');db.backup(backup);backup.close()
        for path in sorted((ROOT/'inbox').glob('*.zip')):
            key=hashlib.sha256(path.read_bytes()).hexdigest()
            try:
                result=import_zip(db,path);result['archive']=key;results.append(result)

                destination=ROOT/'archive'/f'{key}.zip'
            except Exception as e:
                errors.append({'stage':'import','archive':key,'error':type(e).__name__+': '+str(e)})
                destination=ROOT/'quarantine'/f'{key}.zip'
            shutil.move(str(path),str(destination))
            if path.with_suffix('.json').exists():shutil.move(str(path.with_suffix('.json')),str(destination.with_suffix('.json')))
        # Validated files stay in the archive if the secondary registry needs a retry.
        def merge(archived):
            result=subprocess.run([os.environ.get('STATEMENT_REPORT_PYTHON','/home/kocher.av/.report-venv/bin/python'),str(ROOT/'sync_existing.py'),str(archived)],check=True,capture_output=True,text=True)
            return json.loads(result.stdout)
        sync_path=ROOT/'data/sync_state.json'
        synced=json.loads(sync_path.read_text()) if sync_path.exists() else {}
        for archived in (ROOT/'archive').glob('*.zip'):
            if archived.stem in synced:continue
            try:
                synced[archived.stem]=merge(archived)
                tmp=sync_path.with_suffix('.tmp');tmp.write_text(json.dumps(synced,ensure_ascii=False));tmp.replace(sync_path)
            except Exception as exc:errors.append({'stage':'registry_sync','archive':archived.stem,'error':type(exc).__name__})
        # Reports are rebuilt from the authoritative ledger, not appended blindly.
        try:
            subprocess.run([sys.executable,str(ROOT/'ledger.py'),'export'],check=True,capture_output=True)
            if not errors and not (ROOT/'data/posting_paused.json').exists():
                subprocess.run([sys.executable,str(ROOT/'tools/build_finish_company.py')],check=True,capture_output=True)
                subprocess.run([sys.executable,str(ROOT/'tools/build_posting_plan.py')],check=True,capture_output=True)
                plan=json.loads((ROOT/'evidence/posting/plan.json').read_text())
                journal=json.loads((ROOT/'data/posting_journal.json').read_text()).get('operations',{}) if (ROOT/'data/posting_journal.json').exists() else {}
                if any(journal.get(p['key'],{}).get('state')!='linked' for p in plan):
                    subprocess.run(['sudo','-n','/usr/bin/python3',str(ROOT/'tools/run_posting.py')],check=True,capture_output=True,timeout=1500)
                subprocess.run([sys.executable,str(ROOT/'ledger.py'),'export'],check=True,capture_output=True)
            py=os.environ.get('STATEMENT_REPORT_PYTHON','/home/kocher.av/.report-venv/bin/python')
            report_run=subprocess.run([py,str(ROOT/'report.py')],check=True,capture_output=True,text=True)
            report_result=json.loads(report_run.stdout)
        except Exception as e:errors.append({'stage':'report','error':type(e).__name__+': '+str(e)})
        status={'ran_at':dt.datetime.now(dt.timezone.utc).isoformat(),'mail_checked':mail_ok,'imports':results,'errors':errors,'accounts':health(db),'notifications_configured':True,'posting_enabled':not (ROOT/'data/posting_paused.json').exists(),'posting_policy':'trade_cash_separate_from_goods;verified_company_cash;reviewed_paired_movements'}
        status['report']=report_result
        target=ROOT/'reports/status.json';temp=target.with_suffix('.tmp');temp.write_text(json.dumps(status,ensure_ascii=False,indent=2));temp.replace(target)
        from daily_notice import notify_status
        try:notify_status(status)
        except Exception as exc:
            status['notification_error']=type(exc).__name__;target.write_text(json.dumps(status,ensure_ascii=False,indent=2))
        print(json.dumps(status,ensure_ascii=False))
        return 1 if errors else 0
if __name__=='__main__':sys.exit(main())
