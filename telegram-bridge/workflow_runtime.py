"""Durable operations, receipts and owner questions; no Telegram/CRM dependency.

Running operations are never retried automatically after a crash: an external
write may already have succeeded. Recovery records uncertainty for reconciliation.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import uuid


class Conflict(ValueError):
    pass


def stamp():
    return datetime.now(timezone.utc).isoformat(timespec='milliseconds')


def dump(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS operations(
                id TEXT PRIMARY KEY, actor TEXT NOT NULL, scenario TEXT NOT NULL,
                dedup_key TEXT NOT NULL, target TEXT NOT NULL, payload TEXT NOT NULL,
                revision INTEGER NOT NULL DEFAULT 1, status TEXT NOT NULL DEFAULT 'draft',
                receipt TEXT, error TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                UNIQUE(actor, scenario, dedup_key));
            CREATE TABLE IF NOT EXISTS events(
                id INTEGER PRIMARY KEY, operation_id TEXT, event TEXT NOT NULL,
                details TEXT NOT NULL, created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS incoming(
                actor TEXT NOT NULL, update_id TEXT NOT NULL, metadata TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'received', created_at TEXT NOT NULL,
                PRIMARY KEY(actor, update_id));
            CREATE TABLE IF NOT EXISTS questions(
                id TEXT PRIMARY KEY, actor TEXT NOT NULL, code TEXT NOT NULL,
                text TEXT NOT NULL, stage TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'prepared',
                telegram_message_id TEXT, answer TEXT, created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL, UNIQUE(actor,code));
            CREATE TABLE IF NOT EXISTS answers(
                id INTEGER PRIMARY KEY, question_id TEXT NOT NULL REFERENCES questions(id),
                actor TEXT NOT NULL, update_id TEXT NOT NULL, text TEXT NOT NULL,
                created_at TEXT NOT NULL, UNIQUE(actor,update_id));
            CREATE TABLE IF NOT EXISTS views(
                id TEXT PRIMARY KEY, actor TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS controls(
                token TEXT PRIMARY KEY, view_id TEXT NOT NULL REFERENCES views(id),
                label TEXT NOT NULL, used INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS notifications(
                actor TEXT NOT NULL, kind TEXT NOT NULL, object_id TEXT NOT NULL,
                payload TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending', created_at TEXT NOT NULL,
                PRIMARY KEY(actor,kind,object_id));
            ''')
        os.chmod(self.path, 0o600)

    @contextmanager
    def connect(self, transaction=False):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA busy_timeout=10000')
        db.execute('PRAGMA foreign_keys=ON')
        try:
            if transaction:
                db.execute('BEGIN IMMEDIATE')
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def decode(row):
        if row is None:
            return None
        result = dict(row)
        for key in ('payload', 'target', 'receipt'):
            if result.get(key) is not None:
                result[key] = json.loads(result[key])
        return result

    def event(self, db, op, kind, details=None):
        db.execute('INSERT INTO events(operation_id,event,details,created_at) VALUES(?,?,?,?)',
                   (op, kind, dump(details or {}), stamp()))

    def create(self, actor, scenario, key, target, payload):
        serialized_target, serialized_payload = dump(target), dump(payload)
        if not all(str(x).strip() for x in (actor, scenario, key)):
            raise ValueError('Operation identity is required')
        with self.connect(True) as db:
            row = db.execute('SELECT * FROM operations WHERE actor=? AND scenario=? AND dedup_key=?',
                             (str(actor), scenario, str(key))).fetchone()
            if row:
                if row['target'] != serialized_target or row['payload'] != serialized_payload:
                    raise Conflict('Operation key is already bound to another target or payload')
                return self.decode(row)
            conflict=db.execute("SELECT id FROM operations WHERE actor=? AND scenario=? AND target=? AND status IN ('running','uncertain') LIMIT 1",
                                (str(actor),scenario,serialized_target)).fetchone()
            if conflict:
                raise Conflict('Предыдущая запись для этого объекта требует завершения или сверки: '+conflict['id'])
            op = uuid.uuid4().hex
            now = stamp()
            db.execute('INSERT INTO operations(id,actor,scenario,dedup_key,target,payload,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)',
                       (op, str(actor), scenario, str(key), serialized_target, serialized_payload, now, now))
            self.event(db, op, 'created')
            return self.decode(db.execute('SELECT * FROM operations WHERE id=?', (op,)).fetchone())

    def get(self, op):
        with self.connect() as db:
            return self.decode(db.execute('SELECT * FROM operations WHERE id=?', (op,)).fetchone())

    def revise(self, op, revision, payload):
        with self.connect(True) as db:
            updated = db.execute("UPDATE operations SET payload=?,revision=revision+1,updated_at=? WHERE id=? AND revision=? AND status='draft'",
                                 (dump(payload), stamp(), op, revision))
            if not updated.rowcount:
                raise Conflict('Draft is stale or already confirmed')
            self.event(db, op, 'revised', {'from_revision': revision})
        return self.get(op)

    def confirm(self, op, revision):
        with self.connect(True) as db:
            row = db.execute('SELECT * FROM operations WHERE id=?', (op,)).fetchone()
            if not row or row['revision'] != revision or row['status'] not in ('draft', 'confirmed'):
                raise Conflict('Confirmation is stale or operation is not a draft')
            if row['status'] == 'draft':
                db.execute("UPDATE operations SET status='confirmed',updated_at=? WHERE id=?", (stamp(), op))
                self.event(db, op, 'confirmed', {'revision': revision})
        return self.get(op)

    def claim(self, op):
        with self.connect(True) as db:
            changed = db.execute("UPDATE operations SET status='running',updated_at=? WHERE id=? AND status='confirmed'", (stamp(), op))
            if not changed.rowcount:
                return None
            self.event(db, op, 'started')
        return self.get(op)

    def finish(self, op, receipt, status='succeeded', error=None):
        if status not in ('succeeded', 'failed', 'uncertain'):
            raise ValueError('Invalid terminal state')
        with self.connect(True) as db:
            changed = db.execute("UPDATE operations SET status=?,receipt=?,error=?,updated_at=? WHERE id=? AND status='running'",
                                 (status, dump(receipt), error, stamp(), op))
            if not changed.rowcount:
                raise Conflict('Only a running operation can finish')
            self.event(db, op, status)
        return self.get(op)

    def cancel(self, op):
        with self.connect(True) as db:
            changed = db.execute("UPDATE operations SET status='cancelled',updated_at=? WHERE id=? AND status IN ('draft','confirmed')", (stamp(), op))
            if not changed.rowcount:
                raise Conflict('Cannot cancel an operation that may already have external effects')
            self.event(db, op, 'cancelled')

    def recover(self):
        """Call on startup only when no old workers remain. Never re-execute writes."""
        with self.connect(True) as db:
            ids = [row[0] for row in db.execute("SELECT id FROM operations WHERE status='running'")]
            db.execute("UPDATE operations SET status='uncertain',error='Interrupted; reconcile external result',updated_at=? WHERE status='running'", (stamp(),))
            for op in ids:
                self.event(db, op, 'recovery_requires_reconciliation')
            db.execute("UPDATE incoming SET status='needs_review' WHERE status='routing'")
            return ids

    def incoming_status(self,actor,update_id,status):
        if status not in ('routing','routed','needs_review'):raise ValueError('Unknown incoming status')
        with self.connect(True) as db:
            db.execute('UPDATE incoming SET status=? WHERE actor=? AND update_id=?',(status,str(actor),str(update_id)))

    def interrupted_inputs(self,actor):
        with self.connect() as db:
            return [dict(r) for r in db.execute("SELECT update_id,created_at FROM incoming WHERE actor=? AND status='needs_review' ORDER BY created_at",(str(actor),))]

    def receive(self, actor, update_id, metadata):
        with self.connect(True) as db:
            return bool(db.execute('INSERT OR IGNORE INTO incoming(actor,update_id,metadata,created_at) VALUES(?,?,?,?)',
                                   (str(actor), str(update_id), dump(metadata), stamp())).rowcount)

    def unresolved(self, actor=None):
        with self.connect() as db:
            query = "SELECT * FROM operations WHERE status IN ('running','uncertain')"
            args = ()
            if actor is not None:
                query += ' AND actor=?'; args = (str(actor),)
            return [self.decode(row) for row in db.execute(query + ' ORDER BY created_at', args)]

    def reconcile(self, op, revision, actor, outcome, evidence, receipt=None):
        """Operator-only resolution after reading the actual remote state.

        No-effect closes this intent; it never silently retries a financial write.
        A later deliberate operation must use a new reviewed confirmation.
        """
        if outcome not in ('succeeded', 'failed') or not str(evidence).strip():
            raise ValueError('Verified outcome and reconciliation evidence are required')
        if outcome == 'succeeded' and (not isinstance(receipt, dict) or not receipt.get('ok')):
            raise ValueError('Verified success receipt is required')
        with self.connect(True) as db:
            row = db.execute('SELECT * FROM operations WHERE id=?', (op,)).fetchone()
            if not row or row['status'] != 'uncertain' or row['revision'] != revision:
                raise Conflict('Operation is not awaiting reconciliation or revision changed')
            result = receipt if outcome == 'succeeded' else {'ok': False, 'no_effect': True, 'error': 'Проверено: запись отсутствует. Требуется новый просмотр.'}
            db.execute('UPDATE operations SET status=?,receipt=?,error=NULL,revision=revision+1,updated_at=? WHERE id=?',
                       (outcome,dump(result),stamp(),op))
            self.event(db,op,'reconciled',{'actor':str(actor),'outcome':outcome,'evidence':str(evidence)})
        return self.get(op)

    def notify(self, actor, kind, object_id, payload):
        with self.connect(True) as db:
            db.execute('INSERT OR IGNORE INTO notifications(actor,kind,object_id,payload,created_at) VALUES(?,?,?,?,?)',
                       (str(actor),kind,str(object_id),dump(payload),stamp()))

    def notifications(self, actor, kind):
        with self.connect() as db:
            rows=db.execute("SELECT * FROM notifications WHERE actor=? AND kind=? AND status='pending' ORDER BY created_at",
                            (str(actor),kind)).fetchall()
            return [{**dict(row),'payload':json.loads(row['payload'])} for row in rows]

    def dismiss_notification(self, actor, kind, object_id):
        with self.connect(True) as db:
            db.execute("UPDATE notifications SET status='handled' WHERE actor=? AND kind=? AND object_id=?",
                       (str(actor),kind,str(object_id)))

    def question(self, actor, code, text, stage):
        with self.connect(True) as db:
            existing = db.execute('SELECT * FROM questions WHERE actor=? AND code=?', (str(actor), code)).fetchone()
            if existing:
                if existing['text'] != text or existing['stage'] != stage:
                    raise Conflict('Question code already exists with another meaning')
                return dict(existing)
            qid = uuid.uuid4().hex
            now = stamp()
            db.execute('INSERT INTO questions(id,actor,code,text,stage,created_at,updated_at) VALUES(?,?,?,?,?,?,?)',
                       (qid, str(actor), code, text, stage, now, now))
            return dict(db.execute('SELECT * FROM questions WHERE id=?', (qid,)).fetchone())

    def question_sent(self, question_id, message_id):
        with self.connect(True) as db:
            db.execute("UPDATE questions SET telegram_message_id=?,status=CASE WHEN status='prepared' THEN 'sent' ELSE status END,updated_at=? WHERE id=?",
                       (str(message_id), stamp(), question_id))

    def answer(self, actor, message_id, text, update_id, code=None):
        if not str(text).strip():
            return None
        field, value = ('code', code) if code else ('telegram_message_id', str(message_id))
        with self.connect(True) as db:
            row = db.execute(f'SELECT * FROM questions WHERE actor=? AND {field}=?', (str(actor), value)).fetchone()
            if not row:
                return None
            inserted = db.execute('INSERT OR IGNORE INTO answers(question_id,actor,update_id,text,created_at) VALUES(?,?,?,?,?)',
                                  (row['id'], str(actor), str(update_id), text.strip(), stamp()))
            if inserted.rowcount:
                db.execute("UPDATE questions SET answer=?,status='answered',updated_at=? WHERE id=?", (text.strip(), stamp(), row['id']))
            return dict(db.execute('SELECT * FROM questions WHERE id=?', (row['id'],)).fetchone())

    def questions(self, actor):
        with self.connect() as db:
            return [dict(row) for row in db.execute('SELECT * FROM questions WHERE actor=? ORDER BY created_at', (str(actor),))]

    def question_answers(self, qid):
        with self.connect() as db:
            return [dict(row) for row in db.execute('SELECT * FROM answers WHERE question_id=? ORDER BY id', (qid,))]

    def keyboard(self, actor, rows):
        """Bind every control to one actor and one visible screen, not its label."""
        result = []
        with self.connect(True) as db:
            db.execute('UPDATE views SET active=0 WHERE actor=?', (str(actor),))
            obsolete = [row[0] for row in db.execute(
                'SELECT id FROM views WHERE actor=? AND active=0 ORDER BY created_at DESC LIMIT -1 OFFSET 50',
                (str(actor),),
            )]
            if obsolete:
                marks = ','.join('?' for _ in obsolete)
                db.execute(f'DELETE FROM controls WHERE view_id IN ({marks})', obsolete)
                db.execute(f'DELETE FROM views WHERE id IN ({marks})', obsolete)
            view_id = uuid.uuid4().hex
            db.execute('INSERT INTO views(id,actor,created_at) VALUES(?,?,?)', (view_id, str(actor), stamp()))
            for row in rows:
                buttons = []
                for button in row:
                    label = button if isinstance(button, str) else button.get('text')
                    if not label:
                        continue
                    token = uuid.uuid4().hex
                    db.execute('INSERT INTO controls(token,view_id,label) VALUES(?,?,?)', (token, view_id, str(label)))
                    buttons.append({'text': str(label), 'callback_data': 'wf:' + token})
                if buttons:
                    result.append(buttons)
        return {'inline_keyboard': result}

    def take_control(self, actor, token):
        with self.connect(True) as db:
            row = db.execute('SELECT c.*, v.actor, v.active FROM controls c JOIN views v ON v.id=c.view_id WHERE c.token=?', (token,)).fetchone()
            if not row or row['actor'] != str(actor):
                return {'ok': False, 'reason': 'unknown'}
            if row['used']:
                return {'ok': False, 'reason': 'already_used'}
            if not row['active']:
                return {'ok': False, 'reason': 'expired'}
            db.execute('UPDATE controls SET used=1 WHERE token=?', (token,))
            # The entire screen is consumed. Two different confirmation choices
            # racing from the same preview must not both execute.
            db.execute('UPDATE views SET active=0 WHERE id=?', (row['view_id'],))
            return {'ok': True, 'text': row['label'], 'view_id': row['view_id']}

    def invalidate_views(self, actor):
        with self.connect(True) as db:
            db.execute('UPDATE views SET active=0 WHERE actor=?', (str(actor),))
