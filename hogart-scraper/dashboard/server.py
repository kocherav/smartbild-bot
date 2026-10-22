"""Private dashboard API and static app, bound to loopback behind Caddy."""
import hashlib
import hmac
import json
import mimetypes
import os
from pathlib import Path
import secrets
import sqlite3
import threading
import time
from collections import defaultdict, deque
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qsl, urlsplit
import model
import workspace
import shipment_workspace
import shipment_procurement
import matching_store
import supplier_documents
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'finance'))
import allocation_workspace
import allocation_apply
import procurement_workspace

ROOT = Path(__file__).resolve().parent
PREFIX = '/deal-dashboard'
ORIGIN = os.environ.get('DASHBOARD_ORIGIN', 'https://claude.smartbild.su')
DB = Path(os.environ.get('DASHBOARD_DB', str(ROOT / 'data/dashboard.sqlite3')))
SESSION_TTL = 12 * 3600


def read_env(path):
    result = {}
    for line in Path(path).read_text().splitlines():
        if '=' in line and not line.lstrip().startswith('#'):
            key, value = line.split('=', 1); result[key.strip()] = value.strip().strip('"').strip("'")
    return result


def credentials():
    env = read_env('/home/kocher.av/telegram-bridge/.env')
    return env['TELEGRAM_BOT_TOKEN'], {int(env['TELEGRAM_CHAT_ID'])}


def verify_telegram(raw, token, allowed, now=None):
    if not isinstance(raw, str) or len(raw) > 16384: raise ValueError('Invalid auth')
    pairs = parse_qsl(raw, keep_blank_values=True, strict_parsing=True)
    data = dict(pairs)
    if len(data) != len(pairs): raise ValueError('Duplicate auth fields')
    signature = data.pop('hash', '')
    secret = hmac.new(b'WebAppData', token.encode(), hashlib.sha256).digest()
    calculated = hmac.new(secret, '\n'.join(f'{k}={v}' for k, v in sorted(data.items())).encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calculated, signature): raise ValueError('Invalid signature')
    age = (time.time() if now is None else now) - int(data.get('auth_date', '0'))
    if not -30 <= age <= 600: raise ValueError('Expired auth')
    user = json.loads(data.get('user', '{}'))
    if type(user.get('id')) is not int or user['id'] not in allowed: raise ValueError('Not permitted')
    return user['id']


class ClosingConnection(sqlite3.Connection):
    def __exit__(self, *args):
        try: return super().__exit__(*args)
        finally: self.close()


def connect():
    db = sqlite3.connect(DB, timeout=10, factory=ClosingConnection)
    db.row_factory = sqlite3.Row
    return db


def initialize():
    DB.parent.mkdir(exist_ok=True)
    with connect() as db:
        db.executescript('''
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS sessions(hash TEXT PRIMARY KEY, user_id INTEGER, expires REAL);
        CREATE TABLE IF NOT EXISTS codes(hash TEXT PRIMARY KEY, user_id INTEGER, expires REAL);
        CREATE TABLE IF NOT EXISTS tasks(id TEXT PRIMARY KEY, deal_id TEXT NOT NULL, title TEXT NOT NULL,
          owner TEXT NOT NULL, due TEXT NOT NULL, note TEXT NOT NULL, done INTEGER NOT NULL DEFAULT 0,
          revision INTEGER NOT NULL DEFAULT 1, updated_at REAL NOT NULL, actor INTEGER NOT NULL);
        CREATE INDEX IF NOT EXISTS tasks_deal ON tasks(deal_id);
        CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY, at REAL, actor INTEGER, action TEXT, task_id TEXT, payload TEXT);
        ''')
        workspace.initialize(db)
    DB.chmod(0o600)


def digest(value): return hashlib.sha256(value.encode()).hexdigest()


def new_session(user_id):
    token = secrets.token_urlsafe(32)
    with connect() as db:
        db.execute('DELETE FROM sessions WHERE expires < ?', (time.time(),))
        db.execute('DELETE FROM codes WHERE expires < ?', (time.time(),))
        db.execute('INSERT INTO sessions VALUES(?,?,?)', (digest(token), user_id, time.time() + SESSION_TTL))
    return token


def session_user(token):
    if not token or len(token) > 200: return None
    with connect() as db:
        row = db.execute('SELECT user_id FROM sessions WHERE hash=? AND expires>?', (digest(token), time.time())).fetchone()
    if row and row['user_id'] in credentials()[1]: return row['user_id']
    return None


_cache_lock = threading.Lock()
_cache = {'at': 0, 'data': None}

def snapshot():
    with _cache_lock:
        if time.monotonic() - _cache['at'] > 20 or _cache['data'] is None:
            data = model.build()
            _cache.update(at=time.monotonic(), data=data)
        return _cache['data']


def task_rows():
    with connect() as db:
        return [dict(x) for x in db.execute('SELECT * FROM tasks ORDER BY done, due, updated_at DESC')]


def save_task(body, user):
    ident = body.get('id') or secrets.token_hex(12)
    if not isinstance(ident, str) or len(ident) > 100: raise ValueError('Некорректная задача')
    did = str(body.get('deal_id') or '')
    if did not in {d['id'] for d in snapshot()['deals']}: raise ValueError('Сделка не найдена')
    title = str(body.get('title') or '').strip()
    owner = str(body.get('owner') or '').strip()
    due = str(body.get('due') or '')
    note = str(body.get('note') or '').strip()
    if not title or len(title) > 200 or len(owner) > 100 or len(note) > 2000: raise ValueError('Проверьте длину полей задачи')
    if due: date.fromisoformat(due)
    if type(body.get('done', False)) is not bool: raise ValueError('Некорректный статус')
    done = int(body.get('done', False))
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        current = db.execute('SELECT * FROM tasks WHERE id=?', (ident,)).fetchone()
        depends = body.get('depends_on', current['depends_on'] if current else '')
        workspace.validate_dependency(db, ident, did, depends, done)
        if current:
            if current['deal_id'] != did or body.get('revision') != current['revision']: raise Conflict()
            revision = current['revision'] + 1
            db.execute('UPDATE tasks SET title=?,owner=?,due=?,note=?,done=?,revision=?,updated_at=?,actor=? WHERE id=?',
                (title, owner, due, note, done, revision, time.time(), user, ident))
        else:
            if body.get('id'): raise Conflict()
            revision = 1
            db.execute('INSERT INTO tasks(id,deal_id,title,owner,due,note,done,revision,updated_at,actor) VALUES(?,?,?,?,?,?,?,?,?,?)', (ident, did, title, owner, due, note, done, revision, time.time(), user))
        db.execute('UPDATE tasks SET depends_on=? WHERE id=?', (depends, ident))
        body = {**body, 'depends_on': depends}
        db.execute('INSERT INTO audit(at,actor,action,task_id,payload) VALUES(?,?,?,?,?)',
            (time.time(), user, 'update' if current else 'create', ident, json.dumps(body, ensure_ascii=False)))
        return dict(db.execute('SELECT * FROM tasks WHERE id=?', (ident,)).fetchone())


class Conflict(Exception): pass

_rate_lock = threading.Lock()
_rates = defaultdict(deque)

def rate_allowed(key):
    with _rate_lock:
        now = time.monotonic()
        for old_key in list(_rates):
            if not _rates[old_key] or _rates[old_key][-1] < now - 60: del _rates[old_key]
        q = _rates[key]
        while q and q[0] < now - 60: q.popleft()
        if len(q) >= 10: return False
        q.append(now)
        return True


class Server(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 32
    gate = threading.BoundedSemaphore(32)
    def process_request(self, request, client_address):
        if not self.gate.acquire(blocking=False):
            request.close(); return
        super().process_request(request, client_address)
    def process_request_thread(self, request, client_address):
        try: super().process_request_thread(request, client_address)
        finally: self.gate.release()


class Handler(BaseHTTPRequestHandler):
    server_version = 'Dashboard'
    def setup(self):
        super().setup(); self.connection.settimeout(15)
    def log_message(self, fmt, *args):
        # Never log query strings or credentials.
        print(self.command, urlsplit(self.path).path, str(args[1]) if len(args) > 1 else '', flush=True)
    def reply(self, code, data, kind='application/json; charset=utf-8'):
        body = json.dumps(data, ensure_ascii=False, allow_nan=False).encode() if 'application/json' in kind else data
        self.send_response(code)
        self.send_header('Content-Type', kind)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self' https://telegram.org; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; font-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'self' https://web.telegram.org https://*.telegram.org")
        self.end_headers()
        self.wfile.write(body)
    def user(self):
        auth = self.headers.get('Authorization', '')
        return session_user(auth[7:]) if auth.startswith('Bearer ') else None
    def do_GET(self):
        try:
            path = urlsplit(self.path).path
            if path == PREFIX:
                self.send_response(308); self.send_header('Location', PREFIX + '/'); self.end_headers(); return
            if path == PREFIX + '/health': self.reply(200, {'ok': True}); return
            if path.startswith(PREFIX + '/api/'):
                user = self.user()
                if not user: self.reply(401, {'error': 'Откройте дашборд кнопкой в боте'}); return
                if path == PREFIX + '/api/dashboard':
                    snap = snapshot()
                    snap = {**snap, 'deals': shipment_workspace.card_progress(snap['deals'])}
                    with connect() as db: extra = workspace.projection(db, snap['deals'], user)
                    self.reply(200, {**snap, 'tasks': task_rows(), **extra}); return
                if path == PREFIX + '/api/shipments':
                    query=dict(parse_qsl(urlsplit(self.path).query));deal=str(query.get('deal_id',''))
                    card=next((d for d in snapshot()['deals'] if d['id']==deal),None)
                    if not card:self.reply(404,{'error':'Сделка не найдена'});return
                    shipment_view=shipment_workspace.projection(deal)
                    positions=((shipment_view.get('book') or {}).get('data') or {}).get('positions') or []
                    registry=model.load(model.CRM / 'procurement_registry.json', {})
                    decisions=matching_store.project(matching_store.candidates(deal,positions,registry))
                    procurement=shipment_procurement.coverage(deal,positions,registry,decisions)
                    self.reply(200,{**shipment_view,'procurement':procurement,'deal':{'id':deal,'client':card['client'],'total':card['total'],'received':card['received'],'payments_complete':card['payments_complete']}});return
                if path == PREFIX + '/api/supplier-document':
                    query=dict(parse_qsl(urlsplit(self.path).query))
                    try:
                        inv,source,lines=supplier_documents.resolve(model.load(model.CRM / 'procurement_registry.json', {}),query.get('deal_id'),query.get('invoice_id'),query.get('row_id'))
                        action=query.get('action','info')
                        if action=='original': self.reply(200,source.read_bytes(),'application/pdf' if source.suffix.lower()=='.pdf' else 'application/octet-stream');return
                        if action=='page': self.reply(200,supplier_documents.render(source,int(query.get('page','1'))),'image/png');return
                        if action!='info': raise ValueError('Неизвестное действие')
                        info=supplier_documents.describe(source,lines) if source.suffix.lower()=='.pdf' else {'pages':[],'targets':[l.get('source_name','') for l in lines],'first_page':0,'highlighted':False}
                        info['extension']=source.suffix.lower()
                        self.reply(200,{**info,**{k:str(inv.get(k) or '') for k in ('number','date','supplier')}});return
                    except (ValueError,FileNotFoundError) as exc:
                        self.reply(404,{'error':str(exc)});return
                    except Exception:
                        self.reply(503,{'error':'Не удалось открыть PDF. Попробуйте ещё раз или скачайте оригинал.'});return
                if path == PREFIX + '/api/supplier-allocation':
                    self.reply(200, procurement_workspace.projection(snapshot()['deals'])); return
                self.reply(404, {'error': 'Не найдено'}); return
            files = {'/supplier-document':('supplier-document.html','text/html; charset=utf-8'),'/supplier-document.js':('supplier-document.js','text/javascript; charset=utf-8'),'/shipments':('shipments.html','text/html; charset=utf-8'),'/shipments.js':('shipments.js','text/javascript; charset=utf-8'),'/': ('index.html', 'text/html; charset=utf-8'), '/app.js': ('app.js', 'text/javascript; charset=utf-8'),
                '/supplier-allocation': ('supplier-allocation.html', 'text/html; charset=utf-8'),
                '/supplier-allocation.js': ('supplier-allocation.js', 'text/javascript; charset=utf-8'),
                '/workspace.js': ('workspace.js', 'text/javascript; charset=utf-8'), '/style.css': ('style.css', 'text/css; charset=utf-8')}
            suffix = path[len(PREFIX):] if path.startswith(PREFIX + '/') else ''
            if suffix in files:
                filename, kind = files[suffix]; self.reply(200, (ROOT / 'static' / filename).read_bytes(), kind); return
            self.reply(404, {'error': 'Не найдено'})
        except (BrokenPipeError, ConnectionResetError): pass
        except Exception as exc:
            print('GET failed:', type(exc).__name__, flush=True)
            self.reply(503, {'error': 'Данные временно недоступны. Попробуйте обновить страницу.'})
    def do_POST(self):
        try:
            if self.headers.get('Origin') != ORIGIN:
                self.reply(403, {'error': 'Недопустимый источник запроса'}); return
            if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                self.reply(415, {'error': 'Ожидается JSON'}); return
            path = urlsplit(self.path).path
            length = int(self.headers.get('Content-Length', '0'))
            if length <= 0 or length > (22_000_000 if path == PREFIX+'/api/supplier-allocation/document' else 32768): self.reply(413, {'error': 'Размер запроса превышен'}); return
            body = json.loads(self.rfile.read(length))
            if not isinstance(body, dict): raise ValueError('Некорректный запрос')
            path = urlsplit(self.path).path
            if path in (PREFIX + '/api/auth/telegram', PREFIX + '/api/auth/code'):
                if not rate_allowed(self.headers.get('X-Dashboard-IP') or self.client_address[0]):
                    self.reply(429, {'error': 'Слишком много попыток. Подождите минуту.'}); return
                if path.endswith('/telegram'):
                    try: user = verify_telegram(body.get('initData'), *credentials())
                    except (ValueError, TypeError, KeyError):
                        self.reply(403, {'error': 'Не удалось подтвердить доступ. Откройте страницу заново через кнопку в боте.'}); return
                else:
                    code = str(body.get('code') or '').replace('-', '').replace(' ', '').upper()
                    with connect() as db:
                        db.execute('BEGIN IMMEDIATE')
                        row = db.execute('SELECT * FROM codes WHERE hash=? AND expires>?', (digest(code), time.time())).fetchone()
                        if not row: self.reply(403, {'error': 'Код неверен, использован или истёк'}); return
                        user = row['user_id']
                        db.execute('DELETE FROM codes WHERE hash=?', (digest(code),))
                    if user not in credentials()[1]: self.reply(403, {'error': 'Доступ закрыт'}); return
                self.reply(200, {'token': new_session(user)}); return
            user = self.user()
            if not user: self.reply(401, {'error': 'Войдите заново через бота'}); return
            if path == PREFIX+'/api/shipments/match':
                deal=str(body.get('deal_id',''))
                if deal not in {d['id'] for d in snapshot()['deals']}:raise ValueError('Сделка не найдена')
                positions=((shipment_workspace.book(deal) or {}).get('data') or {}).get('positions') or []
                inputs=matching_store.candidates(deal,positions,model.load(model.CRM / 'procurement_registry.json', {}))
                self.reply(200,matching_store.decide(str(body.get('id','')),body.get('action'),user,inputs));return
            if path in (PREFIX+'/api/shipments/load',PREFIX+'/api/shipments/confirm',PREFIX+'/api/shipments/preview'):
                deal=str(body.get('deal_id',''))
                if deal not in {d['id'] for d in snapshot()['deals']}:raise ValueError('Сделка не найдена')
                result=shipment_workspace.request(deal) if path.endswith('/load') else shipment_workspace.preview(body) if path.endswith('/preview') else shipment_workspace.confirm(body,user)
                self.reply(200,result);return
            if path == PREFIX+'/api/supplier-allocation/match':
                registry=model.load(model.CRM / 'procurement_registry.json',{});rows,_=procurement_workspace.ledgers(snapshot()['deals'])
                inputs,_=procurement_workspace.match.candidates(registry,rows)
                self.reply(200,matching_store.decide(str(body.get('id','')),body.get('action'),user,inputs));return
            if path == PREFIX+'/api/supplier-allocation/document':
                if body.get('action')=='new' and str(body.get('deal_id')) not in {str(d['id']) for d in snapshot()['deals'] if not d.get('is_purchase')}:raise ValueError('Сделка не найдена')
                self.reply(200,procurement_workspace.command(body,user));return
            if path in (PREFIX + '/api/supplier-allocation/preview', PREFIX + '/api/supplier-allocation/draft', PREFIX + '/api/supplier-allocation/apply'):
                if path.endswith('/apply'):
                    result=allocation_apply.request(body,snapshot()['deals'],user)
                elif path.endswith('/draft'):
                    result=allocation_workspace.save_draft(body,snapshot()['deals'],user)
                else:
                    procurement=json.loads(allocation_workspace.queue.PROCUREMENT.read_text())
                    result=allocation_apply.public(allocation_apply.prepare(body,snapshot()['deals'],procurement))
                self.reply(200,result); return
            if path == PREFIX + '/api/browser-code':
                code = ''.join(secrets.choice('ABCDEFGHJKLMNPQRSTUVWXYZ23456789') for _ in range(12))
                with connect() as db:
                    db.execute('DELETE FROM codes WHERE user_id=?', (user,))
                    db.execute('INSERT INTO codes VALUES(?,?,?)', (digest(code), user, time.time() + 300))
                self.reply(200, {'code': '-'.join(code[i:i+4] for i in range(0,12,4)), 'expires_in': 300,
                    'url': ORIGIN + PREFIX + '/'}); return
            if path == PREFIX + '/api/logout':
                with connect() as db: db.execute('DELETE FROM sessions WHERE hash=?', (digest(self.headers['Authorization'][7:]),))
                self.reply(200, {'ok': True}); return
            if path == PREFIX + '/api/objects':
                with connect() as db: result = workspace.save_object(db, body, user, snapshot()['deals'])
                self.reply(200, {'object': result}); return
            if path == PREFIX + '/api/plans':
                with connect() as db: result = workspace.save_plan(db, body, user, snapshot()['deals'])
                self.reply(200, {'plan': result}); return
            if path == PREFIX + '/api/history':
                ids = body.get('deal_ids')
                if not isinstance(ids, list) or len(ids)>100 or any(not isinstance(d,str) for d in ids): raise ValueError()
                with connect() as db: result = workspace.history(db, ids)
                self.reply(200, {'history': result}); return
            if path == PREFIX + '/api/views':
                with connect() as db: workspace.save_view(db, body, user)
                self.reply(200, {'ok': True}); return
            if path == PREFIX + '/api/tasks': self.reply(200, {'task': save_task(body, user)}); return
            self.reply(404, {'error': 'Не найдено'})
        except (Conflict, workspace.Conflict, allocation_workspace.Conflict): self.reply(409, {'error': 'Запись уже изменена. Обновите данные и повторите.'})
        except (ValueError, TypeError, KeyError) as exc: self.reply(400, {'error': str(exc) if isinstance(exc, ValueError) and not isinstance(exc, json.JSONDecodeError) and str(exc) else 'Проверьте поля запроса'})
        except (BrokenPipeError, ConnectionResetError): pass
        except Exception as exc:
            print('POST failed:', type(exc).__name__, flush=True)
            self.reply(503, {'error': 'Не удалось выполнить действие. Попробуйте ещё раз.'})

if __name__ == '__main__':
    initialize()
    print('Dashboard listening on loopback:' + os.environ.get('DASHBOARD_PORT', '8096'), flush=True)
    Server(('127.0.0.1', int(os.environ.get('DASHBOARD_PORT', '8096'))), Handler).serve_forever()
