"""Audited operator-only reconciliation of approved legacy work to a CRM row.

No external calls, new accruals or payment changes. An explicit conversion is
required; the original report row and work are retained in the audit receipt.
"""
import json
import math
import sqlite3
from datetime import datetime, timezone
from restore_historical_detail import digest


def preview(path, deal_id, work_id, target, quantities, evidence):
    if not evidence: raise ValueError('Нужен источник подтверждения')
    if not target.get('source_key','').startswith('deal:') or not target.get('unit') or not target.get('name'):
        raise ValueError('Нужна точная позиция сделки и единица')
    db=sqlite3.connect('file:'+str(path)+'?mode=ro',uri=True);db.row_factory=sqlite3.Row
    try:
        work=db.execute('SELECT * FROM work_items WHERE id=? AND deal_id=?',(work_id,str(deal_id))).fetchone()
        if not work:raise ValueError('Работа другой сделки или отсутствует')
        rows=[dict(r) for r in db.execute('SELECT ri.*,r.imported,r.status AS report_status FROM report_items ri JOIN reports r ON r.id=ri.report_id WHERE ri.work_item_id=? ORDER BY ri.id',(work_id,))]
        if not rows or any(not r['imported'] or r['report_status']!='approved' or r['status']!='accepted' for r in rows):
            raise ValueError('Только утверждённые исторические строки')
        if set(quantities)!={r['id'] for r in rows}:raise ValueError('Нужны объёмы всех исторических строк')
        for r in rows:
            q=quantities[r['id']]
            if not math.isfinite(q) or q<=0 or r['accepted_amount'] is None:raise ValueError('Некорректный объём или не зафиксирована сумма')
        for field in ('planned_qty','rate'):
            if not math.isfinite(target[field]) or target[field]<0:raise ValueError('Неверный план или расценка')
        if db.execute('SELECT 1 FROM work_items WHERE deal_id=? AND source_key=? AND id<>?',(str(deal_id),target['source_key'],work_id)).fetchone():
            raise ValueError('Позиция уже связана с другой работой')
        result=dict(work=dict(work),rows=rows,target=target,quantities=quantities,evidence=evidence)
        result['fingerprint']=digest(result);return result
    finally:db.close()


def apply(path, deal_id, work_id, target, quantities, evidence, expected, actor):
    db=sqlite3.connect(path)
    try:
        db.execute('BEGIN IMMEDIATE')
        p=preview(path,deal_id,work_id,target,quantities,evidence)
        if p['fingerprint']!=expected:raise ValueError('История изменилась после проверки')
        db.execute('UPDATE work_items SET source_key=?,name=?,unit=?,planned_qty=?,rate=? WHERE id=?',
            [target[k] for k in ('source_key','name','unit','planned_qty','rate')]+[work_id])
        for item_id,qty in quantities.items():
            db.execute('UPDATE report_items SET declared_qty=?,accepted_qty=? WHERE id=?',(qty,qty,item_id))
        stamp=datetime.now(timezone.utc).isoformat()
        db.execute('INSERT INTO audit_log(deal_id,entity,entity_id,action,actor,payload,created_at) VALUES(?,?,?,?,?,?,?)',
            (str(deal_id),'work',str(work_id),'historical_work_linked',actor,json.dumps(p,ensure_ascii=False),stamp))
        db.execute("INSERT INTO publication_jobs(deal_id,updated_at) VALUES(?,?) ON CONFLICT(deal_id) DO UPDATE SET revision=revision+1,status='pending',updated_at=excluded.updated_at,error=NULL",(str(deal_id),stamp))
        db.commit()
    except Exception:db.rollback();raise
    finally:db.close()


def merge_approved(path,deal_id,keep_id,other_ids,total_qty,evidence,actor):
    """Explicit owner-confirmed combined quantity, same historical report only."""
    if not evidence or not math.isfinite(total_qty) or total_qty<=0:raise ValueError('Нужны подтверждение и объём')
    ids=[keep_id]+list(other_ids)
    if len(set(ids))!=len(ids):raise ValueError('Повтор ID')
    db=sqlite3.connect(path);db.row_factory=sqlite3.Row
    try:
        db.execute('BEGIN IMMEDIATE')
        works=[dict(r) for r in db.execute('SELECT * FROM work_items WHERE deal_id=?',(str(deal_id),)) if r['id'] in ids]
        if len(works)!=len(ids):raise ValueError('Работы другой сделки')
        placeholders=','.join('?' for _ in ids)
        rows=[dict(r) for r in db.execute(f'SELECT ri.*,r.imported,r.status AS report_status FROM report_items ri JOIN reports r ON r.id=ri.report_id WHERE ri.work_item_id IN ({placeholders}) ORDER BY ri.id',ids)]
        if len(rows)!=len(ids) or {r['work_item_id'] for r in rows}!=set(ids) or len({r['report_id'] for r in rows})!=1 or any(not r['imported'] or r['report_status']!='approved' or r['status']!='accepted' or r['accepted_amount'] is None for r in rows):
            raise ValueError('Нужны отдельные принятые строки одного исторического отчёта')
        first=next(r for r in rows if r['work_item_id']==keep_id)
        for r in rows:
            qty=total_qty if r['id']==first['id'] else 0
            db.execute('UPDATE report_items SET work_item_id=?,accepted_qty=?,declared_qty=? WHERE id=?',(keep_id,qty,qty,r['id']))
        for wid in other_ids:db.execute('UPDATE work_items SET active=0 WHERE id=?',(wid,))
        stamp=datetime.now(timezone.utc).isoformat()
        db.execute('INSERT INTO audit_log(deal_id,entity,entity_id,action,actor,payload,created_at) VALUES(?,?,?,?,?,?,?)',
            (str(deal_id),'work',str(keep_id),'historical_work_merged',actor,json.dumps(dict(works=works,rows=rows,total_qty=total_qty,evidence=evidence),ensure_ascii=False),stamp))
        db.execute("INSERT INTO publication_jobs(deal_id,updated_at) VALUES(?,?) ON CONFLICT(deal_id) DO UPDATE SET revision=revision+1,status='pending',updated_at=excluded.updated_at,error=NULL",(str(deal_id),stamp))
        db.commit()
    except Exception:db.rollback();raise
    finally:db.close()
