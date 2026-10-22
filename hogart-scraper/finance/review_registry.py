"""Single working queue. Ledger and procurement are facts, reports are projections.

Stable IDs prevent duplicate tasks. Historical answers are imported once; they
never act as a second live queue. Sync closes tasks only when their underlying
open condition disappears; it never posts money or guesses invoice versions.
"""
import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROCUREMENT = ROOT.parent.parent / 'megaplan-crm/procurement_registry.json'

def read(path, default):
    return json.loads(path.read_text()) if path.exists() else default

def atomic(path, value):
    temp = path.with_name(path.name + f'.{os.getpid()}.tmp')
    try:
        with temp.open('w') as out:
            json.dump(value, out, ensure_ascii=False, indent=2, allow_nan=False)
            out.flush(); os.fsync(out.fileno())
        os.chmod(temp, path.stat().st_mode & 0o777 if path.exists() else 0o660)
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)

def current_tasks(rows, procurement):
    tasks = {}
    for r in rows:
        if r['status'] not in ('Требует уточнения', 'Назначение подтверждено; оформление отдельно'):
            continue
        followup = r['status'] == 'Назначение подтверждено; оформление отдельно'
        key = 'bank:' + r['id']
        owner = 'user' if r.get('owner_question') else 'assistant'
        tasks[key] = dict(id=key, kind='bank_followup' if followup else 'bank_review', owner=owner, state='open',
            bank_ids=[r['id']], company=r['company'], supplier=r['counterparty'],
            inn=r['inn'], category=r['category'], amount_cents=r['amount_cents'],
            invoices=r.get('document_numbers') or r.get('references', ''),
            action=('Назначение уже подтверждено. Проверить первичные документы и завершить оформление без повторного вопроса об объекте. ' + r.get('decision_note','')) if followup else (r.get('owner_question') or '; '.join(r['flags']) or 'Сверить основание операции'),
            evidence=r.get('crm_evidence', ''), bank_row=r)
    for inv in procurement.get('invoices', []):
        stocks = [s for s in procurement.get('unallocated_stock', [])
                  if s.get('document_key') == inv.get('document_key')]
        # Recompute instead of trusting potentially stale summary fields.
        cents = lambda x: round(float(x or 0) * 100)
        remaining = cents(inv.get('total')) - sum(cents(a.get('amount')) for a in inv.get('allocations', []))
        remaining -= sum(cents(a.get('amount')) for s in stocks for a in s.get('allocations', []))
        for s in stocks:
            if cents(s.get('available_amount')) <= 1 and float(s.get('available_qty') or 0) <= 1e-9:
                continue
            key = 'stock:' + s['id']
            tasks[key] = dict(id=key, kind='stock_allocation', state='open', owner='assistant',
                document_key=inv['document_key'], invoices=inv['number'], supplier=inv['supplier'],
                inn=inv.get('supplier_inn', ''), amount_cents=cents(s.get('available_amount')),
                qty=s['available_qty'], name=s['name'], bank_ids=[],
                action='Проверить назначение остатка по сохранённым ответам и сделкам; распределить позиции и себестоимость либо подтвердить хранение на складе',
                evidence={'stock_id':s['id'], 'source_path':inv.get('source_path','')})
        difference = remaining - sum(cents(s.get('available_amount')) for s in stocks)
        if abs(difference) > 1:
            key = 'invoice:' + inv['document_key']
            tasks[key] = dict(id=key, kind='invoice_reconciliation', owner='assistant', state='open',
                document_key=inv['document_key'], invoices=inv['number'], supplier=inv['supplier'],
                inn=inv.get('supplier_inn',''), bank_ids=[], amount_cents=difference,
                action='Сверить версию счёта и основания распределения: остаток в карточке не подтверждён строками склада. Не переносить в другую версию без подтверждения',
                evidence={'source_path':inv.get('source_path','')})
    return tasks

def sync(rows, root=ROOT, procurement=None):
    path=root/'data/review_registry.json';path.parent.mkdir(parents=True,exist_ok=True)
    with path.with_suffix('.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        previous=read(path,{})
        history=previous.get('historical_answers')
        if history is None:
            legacy=read(root/'evidence/finish_all/owner_questions.json',{})
            history=legacy.get('resolved_groups',[])
            # Import unresolved owner questions once with their original context.
            previous['imported_owner_questions']=legacy.get('groups',[])
        if procurement is None:
            procurement=json.loads(PROCUREMENT.read_text())  # Fail closed if a source is unavailable.
        incoming=current_tasks(rows,procurement)
        now=dt.datetime.now(dt.timezone.utc).isoformat()
        tasks=previous.get('tasks',{})
        # A paid movement can still lack its amended invoice. Import this known
        # exception once; posting the payment must not silently close it.
        if not previous.get('followups_migrated'):
            for item in read(root/'evidence/deep_review/non_owner_followup.json',[]):
                if item.get('old_question') != 70:
                    continue
                key='primary-document:' + ':'.join(item['bank_ids'])
                r=next((r for r in rows if r['id'] in item['bank_ids']),None)
                if r:
                    tasks[key]=dict(id=key,kind='primary_document',state='open',owner='assistant',
                        manual=True,bank_ids=item['bank_ids'],supplier=r['counterparty'],
                        inn=r['inn'],company=r['company'],amount_cents=r['amount_cents'],
                        invoices='208098',action=item['task'],evidence=r.get('crm_evidence',''),
                        created_at=now,updated_at=now,history=[])
        for key, task in incoming.items():
            old=tasks.get(key,{})
            task['created_at']=old.get('created_at',now)
            task['updated_at']=now
            task['history']=old.get('history',[])
            if 'workflow' in old:task['workflow']=old['workflow']
            if old.get('state')=='resolved':
                task['history'].append({'at':now,'event':'source_condition_reappeared'})
            tasks[key]=task
        for key, task in tasks.items():
            if task.get('manual'):
                row=next((r for r in rows if r['id'] in task['bank_ids']),None)
                if row:task['bank_row']=row
            if key not in incoming and not task.get('manual') and task['state']!='resolved':
                task.update(state='resolved',updated_at=now,resolution='Открытое условие устранено в первичном реестре')
        # Other modules own specification refreshes and document commands in
        # this same registry. A bank/queue refresh must not erase their state.
        result=dict(previous,schema_version=1,updated_at=now,tasks=tasks,historical_answers=history,followups_migrated=True,
                    allocation_drafts=previous.get('allocation_drafts',{}),workflow_audit=previous.get('workflow_audit',[]),
                    imported_owner_questions=previous.get('imported_owner_questions',[]),
                    sources={'bank':'data/ledger.sqlite','procurement':str(PROCUREMENT)},
                    policy='Only this file is the working queue; reports are generated views; evidence is immutable history')
        atomic(path,result)
        return result

def active(registry):
    return [t for t in registry['tasks'].values() if t['state']=='open']

def owner_context(root=ROOT):
    """Compatibility shape for document intake, without reading obsolete queues."""
    reg=read(root/'data/review_registry.json',{})
    groups=[]
    for t in reg.get('tasks',{}).values():
        if t.get('kind')!='bank_review' or t['state']!='open':continue
        r=t['bank_row']
        from ledger import invoice_refs
        groups.append(dict(number=t['id'],bank_ids=t['bank_ids'],supplier=t['supplier'],
            invoices=r.get('document_numbers') or '; '.join(invoice_refs(r['purpose'])),
            amount_cents=t['amount_cents'],question=t['action'],evidence=t['evidence']))
    return {'groups':groups,'resolved_groups':[
        {**q,'resolved':True} for q in reg.get('historical_answers',[])]}

def document_projection(registry):
    """Legacy JSON shape, derived exclusively from the current queue."""
    from document_review import refs, KNOWN
    result={'source':'data/review_registry.json','generated_at':registry['updated_at'],
            'missing':[],'found':[],'pending_assistant_review':[]}
    excluded={'Покупки по корпоративной карте','Перевод между своими счетами','Взыскание','Штрафы','Страховые взносы','Связь','Выдача под отчёт'}
    for t in active(registry):
        if t['kind'] not in ('bank_review','primary_document'):continue
        r=t['bank_row']
        if r['direction']!='out' or r['group']!='Внешняя' or r['category'] in excluded:continue
        rr=refs(r);known=bool(rr) and all((r['inn'],n) in KNOWN for n in rr)
        row=[r['counterparty'],r['inn'],r['company'],'; '.join(rr) or 'Номер отсутствует',r['date']+' №'+r['number'],1,r['amount_cents']/100,t['action'],t['evidence'],r['purpose']]
        result['found' if known else ('missing' if t['owner']=='user' else 'pending_assistant_review')].append(row)
    return result

def resolve_manual(task_id, evidence, root=ROOT):
    """Close document followup only with an explicit, retained evidence reference."""
    if not evidence.strip():raise ValueError('Укажите документ или основание закрытия')
    path=root/'data/review_registry.json'
    with path.with_suffix('.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        registry=read(path,{})
        task=registry['tasks'][task_id]
        if not task.get('manual'):
            raise ValueError('Исправьте исходные данные платежа/распределения и пересоберите реестр')
        now=dt.datetime.now(dt.timezone.utc).isoformat()
        task.update(state='resolved',resolution=evidence,updated_at=now)
        task.setdefault('history',[]).append({'at':now,'event':'resolved','evidence':evidence})
        atomic(path,registry)

def record_processing_followup(key, evidence, pending, root=ROOT):
    path=root/'data/review_registry.json'
    with path.with_suffix('.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        registry=json.loads(path.read_text())
        old=registry['tasks'].get(key,{})
        if not pending and not old:return
        now=dt.datetime.now(dt.timezone.utc).isoformat()
        registry['tasks'][key]=dict(id=key,kind='processing_followup',manual=True,
            state='open' if pending else 'resolved',owner='assistant',bank_ids=[],amount_cents=0,
            supplier=evidence['supplier'],invoices=evidence['invoices'],company=evidence['company'],
            inn=evidence['inn'],action='; '.join(pending) or 'Все шаги подтверждены',evidence=evidence,
            created_at=old.get('created_at',now),updated_at=now,
            history=old.get('history',[])+[{'at':now,'pending_steps':pending}])
        atomic(path,registry)

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument('--resolve');parser.add_argument('--evidence',default='')
    args=parser.parse_args()
    if args.resolve:resolve_manual(args.resolve,args.evidence)
    from report import main
    main()
