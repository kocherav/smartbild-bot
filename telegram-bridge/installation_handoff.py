"""Durable handoff delivery, independent of dialog state and financial writes."""
import fcntl
import os
import sqlite3
from datetime import datetime, timezone


def deliver(db_path, recipients, send):
    if not os.path.exists(db_path): return {'sent': 0, 'pending': 0}
    sent = pending = 0
    with open(db_path + '.handoff.lock', 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        with sqlite3.connect(db_path) as db:
            db.row_factory = sqlite3.Row
            if not db.execute("SELECT 1 FROM sqlite_master WHERE name='handoff_events'").fetchone():
                return {'sent': 0, 'pending': 0}
            rows = db.execute('''SELECT i.* FROM handoff_events e JOIN installations i USING(deal_id)
                WHERE i.status IN ('transferred','in_progress','review')''').fetchall()
            for row in rows:
                chats = recipients(str(row['installer_ref'] or ''))
                if not chats: pending += 1
                for chat in sorted(chats):
                    if db.execute('SELECT 1 FROM handoff_deliveries WHERE deal_id=? AND chat_id=?',
                                  (row['deal_id'],str(chat))).fetchone(): continue
                    message = ('🛠 Вам передан объект.\n\nСделка №'+row['deal_id']+' — '+row['client']+
                               '\n'+row['essence']+'\n\nОбъект и утверждённая ведомость доступны в «Мои монтажи».\n'
                               'В карточке объекта: «📦 Материалы по счетам» — PDF для телефона и Excel для компьютера, без цен. Перечень не подтверждает доставку.')
                    try: ok = send(str(chat), message)
                    except Exception: ok = False
                    if ok:
                        db.execute('INSERT OR IGNORE INTO handoff_deliveries VALUES(?,?,?)',
                                   (row['deal_id'],str(chat),datetime.now(timezone.utc).isoformat()))
                        db.commit(); sent += 1
                    else: pending += 1
    return {'sent': sent, 'pending': pending}
