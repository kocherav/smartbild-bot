#!/usr/bin/env python3
"""Merge a fully validated ZIP into the existing bot bank registry, preserving assignments."""
import datetime as dt,hashlib,json,sys,tempfile,zipfile,re
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from ledger import parse
sys.path.insert(0,'/home/kocher.av/megaplan-crm')
import bank_statement
from registry_transaction import locked

def commission_group(item):
    p=(item.get('purpose') or '').casefold()
    if item.get('counterparty_inn')!='7728168971' or not re.search(r'комис|ком-я|ком\.',p): return None
    return tuple(item.get(k,'') for k in ('account','date','direction','counterparty_inn','counterparty_account'))


def merge(path):
    staged=[]
    with zipfile.ZipFile(path) as z, tempfile.TemporaryDirectory() as temp:
        members=[i for i in z.infolist() if not i.is_dir()]
        if not members or len(members)>100 or sum(i.file_size for i in members)>30_000_000:raise ValueError('Archive limits exceeded')
        for n,info in enumerate(members):
            if not info.filename.lower().endswith('.txt'):raise ValueError('Unsupported member')
            raw=z.read(info);parse(raw) # All totals/dates validated before touching the existing registry.
            p=Path(temp)/f'{n}.txt';p.write_bytes(raw)
            staged.append((info.filename,hashlib.sha256(raw).hexdigest(),bank_statement.parse_1c(str(p))))
    registry_path=Path(bank_statement.REGISTRY_PATH)
    with locked(registry_path):
        data=bank_statement.load_registry();before=json.dumps(data,ensure_ascii=False,indent=2)
        results=[]
        for name,sha,parsed in staged:
            ids=[x['id'] for x in parsed['operations']]
            if len(ids)!=len(set(ids)):raise ValueError('Existing registry cannot distinguish two operations')
            # A prior record with same date/number/parties/amount but changed text is a revision.
            for new in parsed['operations']:
                comparable=[old for old in data['transactions'] if all(old.get(k)==new.get(k) for k in ('account','date','document_number','direction','counterparty_inn','counterparty_account','amount'))]
                if comparable and any(old['id']!=new['id'] for old in comparable):raise ValueError('Bank revision requires reconciliation')
            fresh=bank_statement.remove_cross_format_duplicates(parsed['operations'],data['transactions'])
            data['transactions'].extend(fresh)
            if sha not in {x.get('sha256') for x in data['imports']}:
                data['imports'].append({'sha256':sha,'name':name,'account':parsed['account'],'period':parsed['period'],'imported_at':dt.datetime.now(dt.timezone.utc).isoformat(),'source':'daily_zip'})
            results.append({'account':parsed['account'],'new':len(fresh),'existing':len(parsed['operations'])-len(fresh)})
        from decimal import Decimal
        for name,sha,parsed in staged:
            if not parsed['operations']:continue
            dates=[dt.datetime.strptime(x['date'],'%d.%m.%Y').date() for x in parsed['operations']]
            for direction,totalkey in [('income','credit_total'),('expense','debit_total')]:
                actual=sum((Decimal(x['amount']) for x in data['transactions'] if x['account']==parsed['account'] and x['direction']==direction and min(dates)<=dt.datetime.strptime(x['date'],'%d.%m.%Y').date()<=max(dates)),Decimal(0))
                if actual!=Decimal(parsed[totalkey]):raise ValueError('Merged bank registry turnover mismatch; no changes saved')
        if json.dumps(data,ensure_ascii=False,indent=2)!=before:
            backup=registry_path.with_name('bank_statement_registry.before_daily_zip.'+dt.datetime.now().strftime('%Y%m%d%H%M%S')+'.json')
            backup.write_text(before);backup.chmod(0o600)
            bank_statement.save_registry(data)
        return {'accounts':results,'total':len(data['transactions']),'assigned_preserved':sum(x.get('status')=='assigned' for x in data['transactions'])}
if __name__=='__main__':print(json.dumps(merge(sys.argv[1]),ensure_ascii=False))
