"""Cross-process CRM budgets and circuit breaker. Never replay a write here."""
import contextlib
import email.utils
import fcntl
import hashlib
import http.client
import json
import os
import re
import sqlite3
import socket
import time
import tempfile
import urllib.error
import urllib.parse
import urllib.request

DB = os.path.join(os.path.dirname(__file__), 'megaplan_transport.sqlite3')
MINUTE_LIMIT = 20
HOUR_LIMIT = 600
BACKGROUND_LIMIT = 400
MIN_INTERVAL = 3.0
NOTICE_INTERVAL = 3600
RECOVERY_QUIET = 600


class ProtectionPause(RuntimeError):
    def __init__(self, message, retry_after=60, retryable=True):
        super().__init__(message)
        self.retry_after=max(1,int(retry_after))
        self.retryable=retryable


def connect():
    db = sqlite3.connect(DB, timeout=10)
    db.row_factory = sqlite3.Row
    db.executescript('''
      CREATE TABLE IF NOT EXISTS calls(id INTEGER PRIMARY KEY, at REAL, host TEXT, method TEXT, path TEXT, status TEXT);
      CREATE INDEX IF NOT EXISTS calls_time ON calls(host,at);
      CREATE TABLE IF NOT EXISTS circuits(host TEXT PRIMARY KEY, until REAL DEFAULT 0, failures INTEGER DEFAULT 0, reason TEXT DEFAULT '');
      CREATE TABLE IF NOT EXISTS endpoints(host TEXT, path TEXT, until REAL, PRIMARY KEY(host,path));
      CREATE TABLE IF NOT EXISTS uncertain(fingerprint TEXT PRIMARY KEY, host TEXT, method TEXT, path TEXT, at REAL);
      CREATE TABLE IF NOT EXISTS notices(host TEXT PRIMARY KEY, state TEXT);
      CREATE TABLE IF NOT EXISTS notice_times(host TEXT PRIMARY KEY, at REAL);
      CREATE TABLE IF NOT EXISTS probes(host TEXT PRIMARY KEY, at REAL, ok INTEGER);
    ''')
    # Endpoint denials are operation-specific.  In particular Megaplan can
    # forbid POST /comment/<id> while allowing GET of that same comment so the
    # caller can verify it is read-only and safely publish a new version.
    columns={row[1] for row in db.execute('PRAGMA table_info(endpoints)')}
    if 'method' not in columns:
        db.execute("ALTER TABLE endpoints ADD COLUMN method TEXT NOT NULL DEFAULT '*'")
    # Preserve active cooldowns created by the old schema, but narrow them from
    # wildcard to the operation that actually received 403.
    db.execute('''UPDATE endpoints SET method=COALESCE((
        SELECT calls.method FROM calls
        WHERE calls.host=endpoints.host AND calls.path=endpoints.path AND calls.status='403'
        ORDER BY calls.at DESC LIMIT 1),method) WHERE method='*' ''')
    db.commit()
    os.chmod(DB,0o600)
    return db


def retry_seconds(value, now):
    try: return max(0,float(value))
    except (ValueError,TypeError):
        try: return max(0,email.utils.parsedate_to_datetime(value).timestamp()-now)
        except (ValueError,TypeError,OverflowError): return 300


def paused(host='cclimat.megaplan.ru'):
    if not os.path.exists(DB): return False
    with connect() as db:
        row=db.execute('SELECT until FROM circuits WHERE host=?',(host,)).fetchone()
        return bool(row and row['until']>time.time())


def reachable(host='cclimat.megaplan.ru',timeout=.7):
    if paused(host):return False
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        row=db.execute('SELECT * FROM probes WHERE host=?',(host,)).fetchone()
        if row and time.time()-row['at']<30:return bool(row['ok'])
        try:
            with socket.create_connection((host,443),timeout=timeout):ok=True
        except OSError:ok=False
        db.execute('INSERT OR REPLACE INTO probes VALUES(?,?,?)',(host,time.time(),int(ok)))
        return ok


def foreground_waiting(directory):
    cutoff=time.time()-65
    for name in os.listdir(directory):
        try:
            if os.path.getmtime(os.path.join(directory,name))>=cutoff:return True
        except FileNotFoundError:pass
    return False


def acquire_slot(lock,background=False):
    """Let interactive work take the next slot instead of starving behind scans."""
    directory=DB+'.waiters';os.makedirs(directory,mode=0o770,exist_ok=True)
    marker=None
    if not background:
        fd,marker=tempfile.mkstemp(prefix='request-',dir=directory);os.close(fd)
    # A long background job (morning brief, 28.10) may wait longer for a free slot:
    # it still yields to every interactive request while waiting.
    wait=float(os.environ.get('MEGAPLAN_BACKGROUND_WAIT') or 10) if background else 30
    deadline=time.monotonic()+wait
    try:
        while True:
            if time.monotonic()>deadline:
                raise ProtectionPause('Мегаплан: очередь запросов занята. Запрос не отправлен; повторите позже.')
            if background and foreground_waiting(directory):
                time.sleep(.1);continue
            try:
                fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
                # A foreground request may have appeared while acquiring flock.
                if background and foreground_waiting(directory):
                    fcntl.flock(lock,fcntl.LOCK_UN);time.sleep(.1);continue
                return
            except BlockingIOError:time.sleep(.1)
    finally:
        if marker:
            try:os.unlink(marker)
            except FileNotFoundError:pass


@contextlib.contextmanager
def urlopen(request, timeout=30):
    url=request.full_url if hasattr(request,'full_url') else request
    parsed=urllib.parse.urlsplit(url);host=(parsed.hostname or '').lower()
    if not (host.endswith('.megaplan.ru') or host=='megaplan.ru'):
        with urllib.request.urlopen(request,timeout=timeout) as response: yield response
        return
    method=request.get_method() if hasattr(request,'get_method') else 'GET'
    path=parsed.path
    auth=path.endswith(('/auth/access_token','/User/authorize.api'))
    # v1 uses POST even for reads. Conservatively regard it as a write unless auth.
    write=method not in ('GET','HEAD','OPTIONS') and not auth
    body=getattr(request,'data',None) or b''
    boundary=re.search(r'boundary=([^; ]+)',request.get_header('Content-type','')) if hasattr(request,'get_header') else None
    if boundary:body=body.replace(boundary.group(1).encode(),b'FIXED-MULTIPART-BOUNDARY')
    fingerprint=hashlib.sha256((method+' '+url).encode()+b'\0'+body).hexdigest()
    with open(DB+'.lock','a') as lock:
        acquire_slot(lock,background=os.environ.get('MEGAPLAN_PRIORITY')=='background')
        with connect() as db:
            now=time.time()
            row=db.execute('SELECT * FROM circuits WHERE host=?',(host,)).fetchone()
            if row and row['until']>now:
                raise ProtectionPause(f"Мегаплан: защитная пауза ({row['reason']}), осталось {int(row['until']-now)+1} сек. Запрос не отправлен.", retry_after=row["until"]-now+1)
            denied=db.execute('SELECT until FROM endpoints WHERE host=? AND path=? AND method IN (?,\'*\')',(host,path,method)).fetchone()
            if denied and denied['until']>now:raise ProtectionPause('Мегаплан: доступ к этой операции отклонён. Повторы временно остановлены; проверьте права.', retryable=False)
            if write and db.execute('SELECT 1 FROM uncertain WHERE fingerprint=?',(fingerprint,)).fetchone():
                raise ProtectionPause('Результат предыдущей записи в Мегаплан неизвестен. Повтор заблокирован до сверки, чтобы не создать дубль.', retryable=False)
            # Check the rolling budget at the actual next dispatch time. Checking
            # before the required spacing falsely rejects request 21 at t=57s,
            # although its legal dispatch at t=60s is outside the first slot.
            last=db.execute('SELECT max(at) FROM calls WHERE host=?',(host,)).fetchone()[0]
            if last is not None:time.sleep(max(0,MIN_INTERVAL-(now-last)))
            now=time.time()
            counts=db.execute('SELECT count(*),sum(at>?) FROM calls WHERE host=? AND at>?',(now-60,host,now-3600)).fetchone()
            budget=BACKGROUND_LIMIT if os.environ.get('MEGAPLAN_PRIORITY')=='background' else HOUR_LIMIT
            if counts[0]>=budget or (counts[1] or 0)>=MINUTE_LIMIT:
                delays=[1]
                for count,limit,window in ((counts[0],budget,3600),(counts[1] or 0,MINUTE_LIMIT,60)):
                    if count>=limit:
                        oldest=db.execute('SELECT at FROM calls WHERE host=? AND at>? ORDER BY at LIMIT 1 OFFSET ?', (host,now-window,count-limit)).fetchone()[0]
                        delays.append(oldest+window-now+1)
                raise ProtectionPause('Достигнут безопасный бюджет запросов к Мегаплану. Запрос не отправлен; повторите позже.', retry_after=max(delays))
            db.execute('DELETE FROM calls WHERE at<?',(now-7*86400,))
            cur=db.execute('INSERT INTO calls(at,host,method,path,status) VALUES(?,?,?,?,?)',(now,host,method,path,'started'))
            call_id=cur.lastrowid
            # Commit the uncertain-write fence BEFORE network I/O: a killed worker
            # cannot lose it. A confirmed response removes it below.
            if write:db.execute('INSERT INTO uncertain VALUES(?,?,?,?,?)',(fingerprint,host,method,path,now))
            db.commit()
            try:
                with urllib.request.urlopen(request,timeout=min(timeout,60)) as response:
                    yield response
                db.execute('UPDATE calls SET status=? WHERE id=?',('ok',call_id))
                if write:db.execute('DELETE FROM uncertain WHERE fingerprint=?',(fingerprint,))
                db.execute("INSERT INTO circuits(host) VALUES(?) ON CONFLICT(host) DO UPDATE SET until=0,failures=0,reason=''",(host,))
                db.commit()
            except (urllib.error.URLError,OSError,ValueError,http.client.HTTPException) as exc:
                status=getattr(exc,'code',None);failures=(row['failures'] if row else 0)+1
                delay=0;reason=str(status or type(exc).__name__)
                if status==429:delay=max(60,retry_seconds(exc.headers.get('Retry-After'),time.time()))
                elif status==401:delay=900
                elif status==403:
                    # A permission denial is not a host outage.  Keep retries of
                    # this exact operation stopped, but allow the caller's
                    # read-only verification/fallback and unrelated requests.
                    delay=0
                    db.execute('INSERT OR REPLACE INTO endpoints(host,path,until,method) VALUES(?,?,?,?)',
                               (host,path,time.time()+1800,method))
                elif status is None or status>=500:delay=min(900,30*2**min(failures-1,5))
                # 4xx is a confirmed rejection, not an uncertain commit.
                if write and status is not None and 400<=status<500:
                    db.execute('DELETE FROM uncertain WHERE fingerprint=?',(fingerprint,))
                db.execute('UPDATE calls SET status=? WHERE id=?',(reason,call_id))
                if delay:
                    db.execute('INSERT OR REPLACE INTO circuits VALUES(?,?,?,?)',(host,time.time()+delay,failures,reason))
                db.commit()
                raise


def notify_status(send):
    """Notify once per outage/recovery; expiration alone is NOT a recovery."""
    if not os.path.exists(DB):return
    with connect() as db:
        count=db.execute('SELECT count(*) FROM uncertain WHERE at<?',(time.time()-120,)).fetchone()[0]
        previous=db.execute("SELECT state FROM notices WHERE host='uncertain-writes'").fetchone()
        if count and (not previous or previous[0]!=str(count)):
            if send(f'⚠️ Неподтверждённых записей в Мегаплан: {count}. Автоматический повтор заблокирован; необходимо сверить результат, чтобы не создать дубли.'):
                db.execute("INSERT OR REPLACE INTO notices VALUES('uncertain-writes',?)",(str(count),));db.commit()
        elif not count and previous:
            db.execute("UPDATE notices SET state='0' WHERE host='uncertain-writes'");db.commit()
        for row in db.execute('SELECT * FROM circuits').fetchall():
            host=row['host']; state=row['reason'] or 'ok'
            previous=db.execute('SELECT state FROM notices WHERE host=?',(host,)).fetchone()
            if (previous and previous[0]==state) or (not previous and state=='ok'):continue
            now=time.time()
            last_notice=db.execute('SELECT at FROM notice_times WHERE host=?',(host,)).fetchone()
            if state!='ok' and last_notice and now-last_notice[0]<NOTICE_INTERVAL:continue
            if state=='ok':
                last_failure=db.execute("SELECT max(at) FROM calls WHERE host=? AND status NOT IN ('ok','started')",(host,)).fetchone()[0]
                blocked=db.execute('SELECT 1 FROM endpoints WHERE host=? AND until>?',(host,now)).fetchone()
                if blocked or (last_failure is not None and now-last_failure<RECOVERY_QUIET):continue
            text=('✅ Мегаплан снова ответил успешно. Неопределённые результаты записей требуют отдельной сверки.' if state=='ok'
                  else f'⚠️ Защита обращений к Мегаплану: {state}. Частые повторы остановлены. Черновики сохранены; неподтверждённые записи нельзя считать выполненными.')
            if send(text):
                db.execute('INSERT OR REPLACE INTO notices VALUES(?,?)',(host,state))
                if state!='ok':db.execute('INSERT OR REPLACE INTO notice_times VALUES(?,?)',(host,now))
                db.commit()
