"""One-time owner-authorized handoff of ongoing legacy objects.

Operator-only; not a bypass in the regular approval UI. Authorization must be
the recorded decision and list the exact deals it covers.
"""
import json
import sqlite3
from datetime import datetime,timezone


def apply(path,deal_id,authorization,actor):
    did=str(deal_id)
    if authorization.get('code')!='Q-MIG-HANDOFF' or authorization.get('status')!='answered' or did not in authorization.get('deal_ids',[]):
        raise ValueError('Нет адресного разрешения владельца')
    if authorization.get('answer')!='Разрешаю передать объекты без проекта и контактов':
        raise ValueError('Не подтверждено исключение для проекта и контактов')
    db=sqlite3.connect(path);db.row_factory=sqlite3.Row
    try:
        db.execute('BEGIN IMMEDIATE')
        row=db.execute('SELECT * FROM installations WHERE deal_id=?',(did,)).fetchone()
        if not row:raise ValueError('Объект не подготовлен')
        if db.execute("SELECT 1 FROM audit_log WHERE deal_id=? AND action='historical_owner_handoff'",(did,)).fetchone():
            return {'already_transferred':True,'deal_id':did}
        if row['status']!='historical':raise ValueError('Состояние изменилось: требуется отдельная сверка')
        address_waiver=authorization.get('address_waiver') or {}
        allow_missing_address=(address_waiver.get('code')=='Q-MIG-ADDRESS' and address_waiver.get('status')=='answered'
            and address_waiver.get('answer')=='Да разрешаю' and did in address_waiver.get('deal_ids',[]))
        if not row['installer_ref'] or not row['installer_name'] or (not row['address'] and not allow_missing_address):
            raise ValueError('Нет исполнителя или адреса')
        if not db.execute('SELECT 1 FROM work_items WHERE deal_id=? AND active=1',(did,)).fetchone():
            raise ValueError('Нет ведомости')
        if db.execute("SELECT 1 FROM reports WHERE deal_id=? AND status NOT IN ('approved','partially_approved')",(did,)).fetchone():
            raise ValueError('Есть незавершённый отчёт')
        stamp=datetime.now(timezone.utc).isoformat()
        # Never expose inherited client contacts without explicit selection.
        # Preserve a deliberately attached project, if one already exists.
        project=bool(db.execute("SELECT 1 FROM project_versions WHERE deal_id=? AND status='active'",(did,)).fetchone())
        db.execute("UPDATE installations SET status='transferred',approved_at=?,transferred_at=?,updated_at=?,project_required=?,contact_name='',contact_phone='',contact_ref=NULL WHERE deal_id=?",(stamp,stamp,stamp,int(project),did))
        if not row['address']:
            db.execute("UPDATE installations SET address='Адрес уточняется' WHERE deal_id=?",(did,))
        db.execute('INSERT INTO audit_log(deal_id,entity,entity_id,action,actor,payload,created_at) VALUES(?,?,?,?,?,?,?)',
            (did,'installation',did,'historical_owner_handoff',actor,json.dumps({'before':dict(row),'authorization':authorization},ensure_ascii=False),stamp))
        db.execute("INSERT INTO publication_jobs(deal_id,updated_at) VALUES(?,?) ON CONFLICT(deal_id) DO UPDATE SET revision=revision+1,status='pending',updated_at=excluded.updated_at,error=NULL",(did,stamp))
        db.commit();return {'deal_id':did,'status':'transferred'}
    except Exception:db.rollback();raise
    finally:db.close()
