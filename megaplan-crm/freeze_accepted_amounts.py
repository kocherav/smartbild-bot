"""Freeze existing accrued values without changing accepted quantities or totals.

Dry-run by default. Apply requires an exact externally supplied expected total.
This is a migration of representation, not approval of another report.
"""
import argparse
from decimal import Decimal
import json
import sqlite3
from installation_workflow import DB, now


def freeze(db, report_id, expected_total=None):
    db.execute('BEGIN IMMEDIATE')
    try:
        rows=db.execute('''SELECT ri.id,ri.accepted_qty,w.rate FROM report_items ri
            JOIN reports r ON r.id=ri.report_id JOIN work_items w ON w.id=ri.work_item_id
            WHERE r.id=? AND r.status IN ('approved','partially_approved')
              AND ri.accepted_amount IS NULL AND ri.accepted_qty>0''',(report_id,)).fetchall()
        amounts=[(Decimal(str(qty))*Decimal(str(rate)), row_id) for row_id,qty,rate in rows]
        total=sum((amount for amount,_ in amounts),Decimal('0'))
        if expected_total is None:
            db.rollback(); return {'rows':len(rows),'total':str(total),'applied':False}
        if total!=Decimal(str(expected_total)):
            raise ValueError('Контрольная сумма не совпала; данные не изменены')
        for amount,row_id in amounts:
            db.execute('UPDATE report_items SET accepted_amount=? WHERE id=? AND accepted_amount IS NULL',(float(amount),row_id))
        report=db.execute('SELECT deal_id FROM reports WHERE id=?',(report_id,)).fetchone()
        db.execute('INSERT INTO audit_log VALUES(NULL,?,?,?,?,?,?,?)',
            (report[0],'report',str(report_id),'freeze_existing_accrual','architecture-migration',
             json.dumps({'rows':len(rows),'unchanged_total':str(total)}),now()))
        db.commit(); return {'rows':len(rows),'total':str(total),'applied':True}
    except Exception:
        db.rollback(); raise


if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('report_id',type=int)
    parser.add_argument('--expected-total'); args=parser.parse_args()
    db=sqlite3.connect(DB)
    try: print(json.dumps(freeze(db,args.report_id,args.expected_total)))
    finally: db.close()
