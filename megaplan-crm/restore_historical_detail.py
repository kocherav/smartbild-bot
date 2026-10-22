"""Restore approved detail in-place, without approving or paying a report again.

Caller owns the database path. Planning is read-only; application requires the
exact plan fingerprint and writes an audit receipt in the same transaction.
"""
import hashlib
import json
import math
import sqlite3
from datetime import datetime, timezone
from openpyxl import load_workbook


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,allow_nan=False).encode()).hexdigest()


def approved_rows(path,sheet):
    book=load_workbook(path,read_only=True,data_only=True)
    try:
        values=list(book[sheet].values)
        header=next(i for i,row in enumerate(values) if len(row)>8 and row[1]=='Позиция монтажной ведомости')
        headings=values[header]
        if headings[7:9]!=('Закрыто в этом отчёте','Сумма этого отчёта'):
            raise ValueError('Не подтверждены колонки текущего выполнения')
        rows=[]
        for source in values[header+1:]:
            if not isinstance(source[0],(int,float)):continue
            qty=float(source[7] or 0);amount=float(source[8] or 0)
            if not math.isfinite(qty) or not math.isfinite(amount) or min(qty,amount)<0:
                raise ValueError('Некорректный исторический объём/сумма')
            if qty==0 and amount==0:continue
            rate=float(source[4] or 0)
            if qty<=0 or not math.isfinite(rate) or abs(qty*rate-amount)>.011:
                raise ValueError('Сумма не совпадает с исторической расценкой')
            rows.append(dict(name=str(source[1]),unit=str(source[2]),qty=qty,amount=amount,
                             rate=rate,planned_qty=float(source[3]),source_row=int(source[0])))
        if not rows:raise ValueError('Нет утверждённого выполнения')
        return rows
    finally:book.close()


def _plan(db,report_id,aggregate_item_id,details):
    report=db.execute('SELECT * FROM reports WHERE id=?',(report_id,)).fetchone()
    if not report or not report['imported'] or report['status']!='approved':
        raise ValueError('Нужен ранее утверждённый исторический отчёт')
    key=f'{report_id}:{aggregate_item_id}:{digest(details)}'
    receipt=db.execute("SELECT payload FROM audit_log WHERE action='restore_approved_detail' AND entity_id=?",(key,)).fetchone()
    if receipt:return {'already_applied':True,'receipt':json.loads(receipt['payload'])}
    rows=[dict(x) for x in db.execute('SELECT * FROM report_items WHERE report_id=? ORDER BY id',(report_id,))]
    target=next((x for x in rows if x['id']==aggregate_item_id),None)
    if not target:raise ValueError('Исходная свёрнутая строка не принадлежит отчёту')
    works=[dict(x) for x in db.execute('SELECT * FROM work_items WHERE deal_id=? ORDER BY id',(report['deal_id'],))]
    old=next(x for x in works if x['id']==target['work_item_id'])
    if not str(old['source_key']).startswith('legacy:') or target['status']!='accepted':
        raise ValueError('Строка не является принятой свёрнутой миграцией')
    previous=target['accepted_amount']
    if previous is None:previous=target['accepted_qty']*old['rate']
    if abs(sum(x['amount'] for x in details)-previous)>.011:
        raise ValueError('Детализация изменяет ранее принятую сумму')
    if db.execute('SELECT COUNT(*) FROM report_items WHERE work_item_id=? AND id<>?',(old['id'],aggregate_item_id)).fetchone()[0]:
        raise ValueError('Свёрнутая позиция использована в других строках; нужна отдельная сверка')
    result={'report':dict(report),'original_item':target,'original_work':old,'details':details,'key':key,'works':works,'rows':rows}
    result['fingerprint']=digest(result)
    return result


def preview(path,report_id,aggregate_item_id,details):
    db=sqlite3.connect('file:'+str(path)+'?mode=ro',uri=True);db.row_factory=sqlite3.Row
    try:return _plan(db,report_id,aggregate_item_id,details)
    finally:db.close()


def apply(path,report_id,aggregate_item_id,details,expected_fingerprint,actor):
    db=sqlite3.connect(path);db.row_factory=sqlite3.Row
    try:
        db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE')
        plan=_plan(db,report_id,aggregate_item_id,details)
        if plan.get('already_applied'):return plan
        if plan['fingerprint']!=expected_fingerprint:raise ValueError('Данные изменились после проверки')
        deal=plan['report']['deal_id'];old=plan['original_work'];stamp=datetime.now(timezone.utc).isoformat()
        item_ids=[]
        for row in details:
            candidates=[w for w in plan['works'] if w['id']!=old['id'] and w['name']==row['name'] and w['unit']==row['unit']]
            if len(candidates)>1:raise ValueError('Неоднозначная позиция существующей ведомости')
            if candidates:
                work_id=candidates[0]['id'] # retain active/excluded status and current plan/rate
            else:
                source=f'restored:{report_id}:{aggregate_item_id}:{row["source_row"]}'
                work_id=db.execute('INSERT INTO work_items(deal_id,source_key,name,unit,planned_qty,rate,sort_order,active) VALUES(?,?,?,?,?,?,?,?)',
                    (deal,source,row['name'],row['unit'],row['planned_qty'],row['rate'],old['sort_order']+len(item_ids),old['active'])).lastrowid
            item_ids.append(db.execute('INSERT INTO report_items(report_id,work_item_id,source_text,declared_qty,accepted_qty,accepted_amount,status) VALUES(?,?,?,?,?,?,?)',
                (report_id,work_id,row['name'],row['qty'],row['qty'],row['amount'],'accepted')).lastrowid)
        # Keep original IDs and the full original values in the audit receipt.
        db.execute("UPDATE report_items SET accepted_qty=0,accepted_amount=0,status='superseded' WHERE id=?",(aggregate_item_id,))
        db.execute('UPDATE work_items SET active=0 WHERE id=?',(old['id'],))
        receipt={'original_item':plan['original_item'],'original_work':old,'details':details,'new_item_ids':item_ids,'amount':sum(r['amount'] for r in details)}
        db.execute('INSERT INTO audit_log(deal_id,entity,entity_id,action,actor,payload,created_at) VALUES(?,?,?,?,?,?,?)',
            (deal,'report',plan['key'],'restore_approved_detail',actor,json.dumps(receipt,ensure_ascii=False,allow_nan=False),stamp))
        db.execute("INSERT INTO publication_jobs(deal_id,updated_at) VALUES(?,?) ON CONFLICT(deal_id) DO UPDATE SET revision=revision+1,status='pending',updated_at=excluded.updated_at,error=NULL",(deal,stamp))
        db.commit();return receipt
    except Exception:db.rollback();raise
    finally:db.close()
