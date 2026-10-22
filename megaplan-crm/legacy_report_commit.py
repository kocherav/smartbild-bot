"""Atomic local acceptance of a reviewed multi-deal installation report.

The caller must confirm the complete preview before accepting. Remote
publications are queued; they are never performed in the acceptance transaction.
"""
from datetime import datetime
import hashlib
import json
import re
import os
import math
import sys
import installation_workflow as iw
from legacy_report_plan import plan
from registry_transaction import transaction

def prepare(session,db):
    deals={str(x.get('deal_id')) for x in (session.get('exceptions') or [])+(session.get('report_lines') or []) if x.get('deal_id')}
    works={}
    for deal in sorted(deals):
        if not db.execute('SELECT 1 FROM installations WHERE deal_id=?',(deal,)).fetchone(): continue
        rows=db.execute('''SELECT w.*,COALESCE(SUM(CASE WHEN r.status IN ('approved','partially_approved')
            THEN ri.accepted_qty ELSE 0 END),0) accepted_qty FROM work_items w
            LEFT JOIN report_items ri ON ri.work_item_id=w.id LEFT JOIN reports r ON r.id=ri.report_id
            WHERE w.deal_id=? AND w.cost_kind='work' GROUP BY w.id ORDER BY w.id''',(deal,)).fetchall()
        works[deal]=[dict(row) for row in rows]
    result=plan(session,works)
    result['candidates_by_deal']=works
    if result['cost_review'] or result.get('materials'):
        # Local procurement evidence is part of the review fingerprint. A newly
        # allocated invoice invalidates the confirmation instead of duplicating it.
        from procurement_workflow import load_json
        data=load_json(os.path.join(os.path.dirname(iw.DB),'procurement_registry.json'),{})
        contexts={deal:[] for deal in deals}
        for invoice in data.get('invoices') or []:
            for allocation in invoice.get('allocations') or []:
                deal=str(allocation.get('deal_id'))
                if deal in contexts:
                    contexts[deal].append({'number':invoice.get('number'),'supplier':invoice.get('supplier'),
                        'allocation':allocation})
        result['material_context']=contexts
        result['fingerprint']=hashlib.sha256(json.dumps({'base':result['fingerprint'],'context':contexts},sort_keys=True,ensure_ascii=False,allow_nan=False).encode()).hexdigest()
    return result

def preview(session):
    db=iw.connect()
    try:
        source=session.get('source_path')
        if source and os.path.isfile(source) and db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='legacy_acceptances'").fetchone():
            digest=hashlib.sha256()
            with open(source,'rb') as stream:
                for block in iter(lambda:stream.read(1024*1024),b''):digest.update(block)
            old=db.execute('SELECT receipt FROM legacy_acceptances WHERE source_digest=?',(digest.hexdigest(),)).fetchone()
            if old:return {'already_accepted':True,'receipt':json.loads(old['receipt']),'source_digest':digest.hexdigest()}
        return prepare(session,db)
    finally:db.close()

@transaction(lambda:os.path.join(os.path.dirname(iw.DB),'procurement_registry.json'))
def accept(session,source_digest,expected_fingerprint,actor):
    if not re.fullmatch(r'[a-f0-9]{64}',str(source_digest)):
        raise ValueError('Нужен SHA-256 оригинала отчёта')
    report_date=str(session.get('report_date') or session.get('report') or '')
    datetime.strptime(report_date,'%d.%m.%Y')
    payable=float(session.get('payable_amount') if session.get('payable_amount') is not None else session.get('net_total'))
    if not math.isfinite(payable) or payable<0:raise ValueError('Не подтверждена сумма взаиморасчётов')
    payload_hash=hashlib.sha256(json.dumps(session,sort_keys=True,ensure_ascii=False,allow_nan=False).encode()).hexdigest()
    db=iw.connect()
    try:
        db.execute('''CREATE TABLE IF NOT EXISTS legacy_acceptances(source_digest TEXT PRIMARY KEY,
            payload_hash TEXT NOT NULL,receipt TEXT NOT NULL,created_at TEXT NOT NULL)''')
        db.commit(); db.execute('BEGIN IMMEDIATE')
        old=db.execute('SELECT * FROM legacy_acceptances WHERE source_digest=?',(source_digest,)).fetchone()
        if old:
            if old['payload_hash']!=payload_hash: raise ValueError('Этот оригинал уже принят с другими данными; нужна корректировка, не повторное начисление')
            return {**json.loads(old['receipt']),'duplicate':True}
        from report_media_store import retain
        source=session.get('source_path')
        if not source:raise ValueError('Нет оригинала сборного отчёта')
        retained,digest,size=retain(source,os.path.join(os.path.dirname(iw.DB),'report_sources'))
        if digest!=source_digest:raise ValueError('Оригинал отчёта изменился после предварительного просмотра')
        preview=prepare(session,db)
        if preview['fingerprint']!=expected_fingerprint: raise ValueError('Ведомость или выполнение изменились после просмотра')
        if not preview['ready']: raise ValueError('Остались строки, требующие сопоставления')
        reports=[]
        materials=[r for r in preview.get('materials') or [] if r['cost_decision']=='additional']
        extras=preview.get('additional_costs') or []
        for deal in sorted({row['deal_id'] for row in preview['matched']+materials+extras}):
            number=db.execute('SELECT COALESCE(MAX(report_no),0)+1 FROM reports WHERE deal_id=?',(deal,)).fetchone()[0]
            stamp=iw.now()
            report_id=db.execute('''INSERT INTO reports(deal_id,report_no,status,report_date,raw_text,
                approved_at,approved_by,external_id,source_path,imported) VALUES(?,?,?,?,?,?,?,?,?,0)''',
                (deal,number,'approved',report_date,'Принятый сборный отчёт',stamp,str(actor),f'legacy-accepted:{source_digest}:deal-{deal}',retained)).lastrowid
            db.execute('INSERT INTO media(report_id,telegram_unique_id,local_path,original_name,mime_type,size,sha256,created_at) VALUES(?,?,?,?,?,?,?,?)',
                       (report_id,'legacy-source:'+source_digest,retained,os.path.basename(source),'application/octet-stream',size,source_digest,stamp))
            db.execute('INSERT INTO report_publications(report_id,updated_at) VALUES(?,?)',(report_id,stamp))
            for row in preview['matched']:
                if row['deal_id']!=deal: continue
                db.execute('''INSERT INTO report_items(report_id,work_item_id,source_text,declared_qty,accepted_qty,
                    accepted_amount,status) VALUES(?,?,?,?,?,?,?)''',(report_id,int(row['work_item_id']),row['name'],
                    float(row['quantity']),float(row['quantity']),float(row['amount']),'accepted'))
            for row in materials:
                if row['deal_id']!=deal:continue
                work_id=db.execute("INSERT INTO work_items(deal_id,source_key,name,unit,planned_qty,rate,sort_order,cost_kind) VALUES(?,?,?,?,?,?,?,?)",
                    (deal,f"material-report:{source_digest}:{row['source_key']}",row.get('source') or 'Материалы монтажника','усл.',1,float(row['amount']),9999,'material')).lastrowid
                db.execute("INSERT INTO report_items(report_id,work_item_id,source_text,declared_qty,accepted_qty,accepted_amount,status) VALUES(?,?,?,?,?,?,?)",
                    (report_id,work_id,row.get('source'),1,1,float(row['amount']),'accepted'))
            for row in extras:
                if row['deal_id']!=deal:continue
                work_id=db.execute("INSERT INTO work_items(deal_id,source_key,name,unit,planned_qty,rate,sort_order,cost_kind) VALUES(?,?,?,?,?,?,?,?)",
                    (deal,f"extra-report:{source_digest}:{row['source_key']}",row['name'],'',0,0,9999,'extra_work')).lastrowid
                db.execute("INSERT INTO report_items(report_id,work_item_id,source_text,declared_qty,accepted_qty,accepted_amount,status) VALUES(?,?,?,?,?,?,?)",
                    (report_id,work_id,row['name'],0,0,float(row['amount']),'accepted'))
            iw.enqueue_publication(db,deal)
            iw.audit(db,deal,'report',report_id,'legacy_report_accepted',actor,{'source_digest':source_digest})
            reports.append({'deal_id':deal,'report_id':report_id})
        receipt={'reports':reports,'total':preview['total'],'materials_total':sum(float(r['amount']) for r in materials),
                 'additional_costs':extras,'additional_total':sum(float(r['amount']) for r in extras),'material_decisions':preview.get('materials') or [],'publication_pending':True}
        projection={'source_path':retained,'report_date':report_date,'report':session.get('report'),
                    'payable_amount':payable,'exceptions':[{'deal_id':r['deal_id']} for r in reports]}
        db.execute('INSERT INTO legacy_ledger_jobs(source_digest,payload,updated_at) VALUES(?,?,?)',
                   (source_digest,json.dumps(projection,ensure_ascii=False,allow_nan=False),iw.now()))
        db.execute('INSERT INTO legacy_acceptances VALUES(?,?,?,?)',(source_digest,payload_hash,json.dumps(receipt),iw.now()))
        db.commit(); return receipt
    except Exception:
        db.rollback(); raise
    finally: db.close()

def sync_ledger(source_digest=None,limit=1):
    """Project only immutable, committed acceptances. Never accept a UI payload."""
    from registry_transaction import locked
    bridge_dir=os.path.join(os.path.dirname(os.path.dirname(__file__)),'telegram-bridge')
    if bridge_dir not in sys.path:sys.path.append(bridge_dir)
    import installer_settlements
    with locked(iw.DB+'.legacy-ledger'):
        db=iw.connect()
        try:
            query="SELECT * FROM legacy_ledger_jobs WHERE status='pending'"
            params=[]
            if source_digest:query+=' AND source_digest=?'; params.append(source_digest)
            else:query+=" AND (error IS NULL OR (julianday('now')-julianday(updated_at))*86400>=300)"
            query+=' ORDER BY updated_at LIMIT ?'; params.append(max(1,min(int(limit),5)))
            rows=db.execute(query,params).fetchall()
        finally:db.close()
        failures={}
        for row in rows:
            error=None
            try:
                payload=json.loads(row['payload'])
                if installer_settlements.digest_file(payload['source_path'])!=row['source_digest']:
                    raise ValueError('Сохранённый оригинал отчёта повреждён')
                installer_settlements.record_accrual(payload)
            except Exception as exc:error=type(exc).__name__
            db=iw.connect()
            try:
                db.execute('UPDATE legacy_ledger_jobs SET status=?,error=?,updated_at=? WHERE source_digest=?',
                    ('pending' if error else 'done',error,iw.now(),row['source_digest']))
                db.commit()
            finally:db.close()
            if error:failures[row['source_digest']]=error
        return {'pending_errors':failures}
