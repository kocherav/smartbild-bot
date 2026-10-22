"""Read-only combined settlement view. Never rewrites historical allocations."""
import copy
import json
import os
import sqlite3


def combined(legacy,path,installer_ref='1000142'):
    data=copy.deepcopy(legacy)
    if not os.path.exists(path):return data
    db=sqlite3.connect('file:'+str(path)+'?mode=ro',uri=True);db.row_factory=sqlite3.Row
    try:
        tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {'reports','report_items','work_items','installations','payments'}<=tables:return data
        reports=db.execute("""SELECT r.*,COALESCE(SUM(COALESCE(ri.accepted_amount,ri.accepted_qty*w.rate)),0) AS amount
          FROM reports r JOIN installations i ON i.deal_id=r.deal_id
          LEFT JOIN report_items ri ON ri.report_id=r.id LEFT JOIN work_items w ON w.id=ri.work_item_id
          WHERE i.installer_ref=? AND r.imported=0 AND r.status IN ('approved','partially_approved')
          AND COALESCE(r.external_id,'') NOT LIKE 'legacy-accepted:%' GROUP BY r.id""",(str(installer_ref),)).fetchall()
        for row in reports:
            data['operations'].append(dict(id='native-report:'+str(row['id']),type='accrual',date=row['report_date'],
                amount=row['amount'],deals=[row['deal_id']],display_name=f"Монтажный отчёт №{row['report_no']} — сделка №{row['deal_id']}",
                created_at=row['approved_at'] or '',source_file=os.path.basename(row['source_path'] or ''),origin='installation'))
        # An accepted collected report may still await its ledger projection.
        if 'legacy_ledger_jobs' in tables:
            for row in db.execute('SELECT source_digest,payload FROM legacy_ledger_jobs'):
                payload=json.loads(row['payload'])
                matches=[op for op in data['operations'] if op.get('type')=='accrual' and op.get('source_hash')==row['source_digest']]
                if matches:
                    if len(matches)!=1 or abs(float(matches[0]['amount'])-float(payload['payable_amount']))>.01:raise ValueError('Расхождение начисления сборного отчёта')
                    continue
                data['operations'].append(dict(id='pending-report:'+row['source_digest'],source_hash=row['source_digest'],type='accrual',
                    date=payload['report_date'],amount=payload['payable_amount'],deals=sorted({str(r['deal_id']) for r in payload.get('exceptions',[]) if r.get('deal_id')}),
                    display_name='Принятый сборный отчёт от '+payload['report_date'],created_at='',source_file=os.path.basename(payload['source_path']),origin='installation'))
        payments=db.execute('SELECT p.* FROM payments p JOIN installations i ON i.deal_id=p.deal_id WHERE i.installer_ref=?',(str(installer_ref),)).fetchall()
        for row in payments:
            identities={str(row['external_id'] or ''),str(row['request_id'] or '')}-{''}
            matches=[op for op in data['operations'] if op.get('type')=='payment' and identities.intersection({str(op.get(k) or '') for k in ('external_id','request_id','source_hash')})]
            gross=float(row['amount']);credit=float(row['settlement_amount'] if row['settlement_amount'] is not None else gross)
            if matches:
                if len(matches)!=1 or abs(float(matches[0].get('settlement_amount',matches[0]['amount']))-credit)>.01:raise ValueError('Расхождение выплаты между реестрами')
                continue
            if any(op.get('type')=='payment' and op.get('date')==row['payment_date'] and abs(float(op.get('gross_amount',op['amount']))-gross)<.01 for op in legacy['operations']):
                raise ValueError('Нужна сверка возможного дубля выплаты: '+row['payment_date'])
            data['operations'].append(dict(id='native-payment:'+str(row['id']),type='payment',date=row['payment_date'],amount=gross,
                gross_amount=gross,settlement_amount=credit,coefficient=row['coefficient'],payment_method='cashless' if row['source']=='bank' else 'cash',
                display_name='Выплата по сделке №'+row['deal_id'],number=row['request_id'] or row['external_id'],purpose=row['comment'],
                created_at=row['created_at'],unallocated_advance=credit,origin='installation'))
        return data
    finally:db.close()
