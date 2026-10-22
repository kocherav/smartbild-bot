"""Object workspace, plans and read-only installation projection. No CRM writes."""
from datetime import date, datetime
from pathlib import Path
import json
import re
import sqlite3
import time

INSTALLATIONS = Path('/home/kocher.av/megaplan-crm/installations.sqlite3')

class Conflict(Exception): pass

def initialize(db):
    db.executescript('''
    CREATE TABLE IF NOT EXISTS objects(id TEXT PRIMARY KEY, name TEXT NOT NULL, address TEXT NOT NULL,
      revision INTEGER NOT NULL, updated_at REAL NOT NULL, actor INTEGER NOT NULL);
    CREATE TABLE IF NOT EXISTS object_deals(deal_id TEXT PRIMARY KEY, object_id TEXT NOT NULL);
    CREATE INDEX IF NOT EXISTS object_links ON object_deals(object_id);
    CREATE TABLE IF NOT EXISTS plans(id TEXT PRIMARY KEY, deal_id TEXT NOT NULL, kind TEXT NOT NULL,
      title TEXT NOT NULL, due TEXT NOT NULL, certainty TEXT NOT NULL, amount INTEGER,
      owner TEXT NOT NULL, note TEXT NOT NULL, status TEXT NOT NULL, revision INTEGER NOT NULL,
      updated_at REAL NOT NULL, actor INTEGER NOT NULL);
    CREATE TABLE IF NOT EXISTS workspace_audit(id INTEGER PRIMARY KEY, at REAL NOT NULL, actor INTEGER NOT NULL,
      entity TEXT NOT NULL, entity_id TEXT NOT NULL, deal_ids TEXT NOT NULL, payload TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS saved_views(id TEXT PRIMARY KEY, actor INTEGER NOT NULL, name TEXT NOT NULL,
      filters TEXT NOT NULL);
    ''')
    if 'depends_on' not in [r[1] for r in db.execute('PRAGMA table_info(tasks)')]:
        db.execute("ALTER TABLE tasks ADD COLUMN depends_on TEXT NOT NULL DEFAULT ''")
    db.execute('PRAGMA user_version=2')

def text(body, key, limit, required=False):
    v=body.get(key, '')
    if not isinstance(v,str) or len(v)>limit or (required and not v.strip()):
        raise ValueError('Проверьте поле '+key)
    return v.strip()

def ident(body):
    v=text(body,'id',80,True)
    if not re.fullmatch(r'[a-zA-Z0-9_-]{8,80}',v): raise ValueError('Некорректный идентификатор')
    if type(body.get('revision')) is not int or body['revision']<0: raise ValueError('Нужна версия записи')
    return v

def audit(db,user,entity,oid,ids,before,after):
    db.execute('INSERT INTO workspace_audit(at,actor,entity,entity_id,deal_ids,payload) VALUES(?,?,?,?,?,?)',
      (time.time(),user,entity,oid,json.dumps(sorted(set(ids))),json.dumps({'before':before,'after':after},ensure_ascii=False)))

def save_object(db,body,user,deals):
    oid=ident(body); name=text(body,'name',160,True); address=text(body,'address',400)
    ids=body.get('deal_ids')
    valid={d['id'] for d in deals if not d['is_purchase']}
    if not isinstance(ids,list) or not 1<=len(ids)<=100 or any(not isinstance(x,str) or x not in valid for x in ids) or len(set(ids))!=len(ids):
        raise ValueError('Выберите от 1 до 100 различных сделок продаж')
    db.execute('BEGIN IMMEDIATE')
    old=db.execute('SELECT * FROM objects WHERE id=?',(oid,)).fetchone()
    if body['revision']!=(old['revision'] if old else 0): raise Conflict()
    prev=[r[0] for r in db.execute('SELECT deal_id FROM object_deals WHERE object_id=?',(oid,))]
    for did in ids:
        link=db.execute('SELECT object_id FROM object_deals WHERE deal_id=?',(did,)).fetchone()
        if link and link[0]!=oid: raise ValueError('Сделка '+did+' уже связана с другим объектом. Сначала измените её связь там.')
    # A dependency must remain within one resulting object (or one unlinked deal).
    future={r['deal_id']:r['object_id'] for r in db.execute('SELECT * FROM object_deals') if r['object_id']!=oid}
    future.update({did:oid for did in ids})
    for t in db.execute('SELECT a.deal_id AS a,b.deal_id AS b FROM tasks a JOIN tasks b ON b.id=a.depends_on'):
        if future.get(t['a'],'deal:'+t['a'])!=future.get(t['b'],'deal:'+t['b']):
            raise ValueError('Сначала уберите зависимости задач между разделяемыми сделками')
    rev=body['revision']+1
    db.execute('INSERT INTO objects VALUES(?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,address=excluded.address,revision=excluded.revision,updated_at=excluded.updated_at,actor=excluded.actor',
      (oid,name,address,rev,time.time(),user))
    db.execute('DELETE FROM object_deals WHERE object_id=?',(oid,))
    db.executemany('INSERT INTO object_deals VALUES(?,?)',[(did,oid) for did in ids])
    out={'id':oid,'name':name,'address':address,'revision':rev,'deal_ids':ids}
    audit(db,user,'object',oid,prev+ids,({**dict(old),'deal_ids':prev} if old else None),out)
    return out

def save_plan(db,body,user,deals):
    pid=ident(body); did=text(body,'deal_id',80,True)
    if did not in {d['id'] for d in deals if not d['is_purchase']}: raise ValueError('Сделка не найдена')
    kind=body.get('kind'); certainty=body.get('certainty'); status=body.get('status')
    if kind not in ('income','expense','delivery') or certainty not in ('tentative','agreed') or status not in ('open','done','cancelled'): raise ValueError('Некорректный тип или статус')
    due=text(body,'due',10,True)
    if date.fromisoformat(due).isoformat()!=due: raise ValueError('Некорректная дата')
    title=text(body,'title',200,True); owner=text(body,'owner',100); note=text(body,'note',2000)
    amount=body.get('amount')
    if kind=='delivery': amount=None
    elif type(amount) is not int or not 0<amount<=10**14: raise ValueError('Укажите положительную сумму в копейках')
    if certainty=='agreed' and not note: raise ValueError('Для согласованного срока укажите основание в комментарии')
    db.execute('BEGIN IMMEDIATE')
    old=db.execute('SELECT * FROM plans WHERE id=?',(pid,)).fetchone()
    if body['revision']!=(old['revision'] if old else 0) or (old and old['deal_id']!=did): raise Conflict()
    fields=(pid,did,kind,title,due,certainty,amount,owner,note,status,body['revision']+1,time.time(),user)
    db.execute('INSERT INTO plans VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET kind=excluded.kind,title=excluded.title,due=excluded.due,certainty=excluded.certainty,amount=excluded.amount,owner=excluded.owner,note=excluded.note,status=excluded.status,revision=excluded.revision,updated_at=excluded.updated_at,actor=excluded.actor',fields)
    out=dict(db.execute('SELECT * FROM plans WHERE id=?',(pid,)).fetchone())
    audit(db,user,'plan',pid,[did],dict(old) if old else None,out)
    return out

def validate_dependency(db,task_id,did,depends,done):
    if not isinstance(depends,str) or len(depends)>100: raise ValueError('Некорректная зависимость')
    if depends:
        parent=db.execute('SELECT * FROM tasks WHERE id=?',(depends,)).fetchone()
        if not parent: raise ValueError('Предыдущая задача не найдена')
        def obj(deal):
            r=db.execute('SELECT object_id FROM object_deals WHERE deal_id=?',(deal,)).fetchone()
            return r[0] if r else 'deal:'+deal
        if obj(did)!=obj(parent['deal_id']): raise ValueError('Зависимость должна быть внутри объекта')
        if done and not parent['done']: raise ValueError('Сначала завершите предыдущую задачу')
        seen={task_id}; cur=depends
        while cur:
            if cur in seen: raise ValueError('Циклическая зависимость задач')
            seen.add(cur)
            row=db.execute('SELECT depends_on FROM tasks WHERE id=?',(cur,)).fetchone()
            cur=row[0] if row else ''
    if not done and db.execute('SELECT 1 FROM tasks WHERE depends_on=? AND done=1',(task_id,)).fetchone():
        raise ValueError('Сначала верните в работу выполненные зависимые задачи')

def source_day(value):
    raw=str(value or '').strip()
    for fmt in ('%Y-%m-%d','%d.%m.%Y'):
        try: return datetime.strptime(raw,fmt).date().isoformat()
        except ValueError: pass
    return ''


def installations(path=INSTALLATIONS):
    """Read snapshot transaction, no external imports or source schema changes."""
    if not path.exists(): return {}, 'missing'
    db=None
    try:
        db=sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True,timeout=3)
        db.row_factory=sqlite3.Row; db.execute('PRAGMA query_only=ON'); db.execute('BEGIN')
        out={}
        for r in db.execute('SELECT deal_id,client,address,installer_name,status,updated_at FROM installations'):
            d=dict(r); did=d['deal_id']
            d['works']=[dict(w) for w in db.execute("SELECT id,name,unit,planned_qty,rate FROM work_items WHERE deal_id=? AND active=1 AND cost_kind='work' ORDER BY sort_order,id",(did,))]
            accepted={r['work_item_id']:dict(r) for r in db.execute("""SELECT ri.work_item_id,SUM(COALESCE(ri.accepted_qty,0)) AS qty FROM report_items ri JOIN reports r ON r.id=ri.report_id WHERE r.deal_id=? AND r.status IN ('approved','partially_approved') GROUP BY ri.work_item_id""",(did,))}
            for w in d['works']:
                w['accepted_qty']=accepted.get(w['id'],{}).get('qty',0)
                w.pop('rate',None)
            d['reports']=[dict(r) for r in db.execute('SELECT id,report_no,status,report_date,approved_at,manager_comment FROM reports WHERE deal_id=? ORDER BY report_date DESC,report_no DESC',(did,))]
            for report in d['reports']:
                report['report_date_source']=report['report_date']
                report['report_date']=source_day(report['report_date'])
            d['reports'].sort(key=lambda r:(r['report_date'],r['report_no']),reverse=True)
            d['documents']=[dict(r) for r in db.execute('SELECT p.name,p.created_at,v.version_no,v.status FROM project_documents p JOIN project_versions v ON v.id=p.version_id WHERE v.deal_id=? ORDER BY v.version_no DESC,p.id',(did,))]
            out[did]=d
        return out,'ok'
    except (sqlite3.Error,OSError): return {},'unavailable'
    finally:
        if db is not None: db.close()

def projection(db,deals,user,installation_data=None):
    src,status=installation_data if installation_data is not None else installations()
    objects=[dict(r) for r in db.execute('SELECT * FROM objects ORDER BY updated_at DESC')]
    links={r['deal_id']:r['object_id'] for r in db.execute('SELECT * FROM object_deals')}
    valid={d['id']:d for d in deals if not d['is_purchase']}
    for o in objects:
        o['deal_ids']=[did for did,oid in links.items() if oid==o['id']]
        o['confirmed']=True
        o['missing_deal_ids']=[did for did in o['deal_ids'] if did not in valid]
    for d in valid.values():
        if d['id'] not in links:
            ins=src.get(d['id'],{})
            objects.append({'id':'deal:'+d['id'],'name':d['client'],'address':d['address'] or ins.get('address',''),
              'deal_ids':[d['id']],'confirmed':False,'revision':0,'missing_deal_ids':[]})
    return {'objects':objects,'plans':[dict(r) for r in db.execute('SELECT * FROM plans ORDER BY due,id')],
      'installations':src,'installation_status':status,
      'views':[{**dict(r),'filters':json.loads(r['filters'])} for r in db.execute('SELECT id,name,filters FROM saved_views WHERE actor=? ORDER BY name',(user,))]}

def history(db,ids):
    rows=[]
    # Object histories include both previous and new membership, including detached deals.
    for r in db.execute('SELECT * FROM workspace_audit ORDER BY id DESC'):
        if set(json.loads(r['deal_ids'])) & set(ids):
            d=dict(r); d['payload']=json.loads(d['payload']); d.pop('deal_ids'); rows.append(d)
        if len(rows)>=100: break
    marks=','.join('?' for _ in ids)
    if ids:
        for r in db.execute(f'SELECT a.* FROM audit a JOIN tasks t ON t.id=a.task_id WHERE t.deal_id IN ({marks}) ORDER BY a.id DESC LIMIT 100',ids):
            d=dict(r); rows.append({'at':d['at'],'actor':d['actor'],'entity':'task','entity_id':d['task_id'],'payload':{'after':json.loads(d['payload'])}})
    return sorted(rows,key=lambda r:r['at'],reverse=True)[:100]

def save_view(db,body,user):
    vid=text(body,'id',80,True)
    if not re.fullmatch(r'[a-zA-Z0-9_-]{8,80}',vid): raise ValueError('Некорректный идентификатор')
    if body.get('delete') is True:
        db.execute('DELETE FROM saved_views WHERE id=? AND actor=?',(vid,user)); return
    name=text(body,'name',60,True); filters=body.get('filters')
    allowed={'result','year','manager','company','search','nav','sort','weeks','alert','stage','week','hideZero'}
    if not isinstance(filters,dict) or set(filters)-allowed or any(not isinstance(v,str) or len(v)>400 for v in filters.values()): raise ValueError('Некорректные фильтры')
    if filters.get('hideZero','') not in ('','1'): raise ValueError('Некорректный фильтр нулевых сделок')
    if filters.get('nav','overview') not in ('overview','deals','procurement','tasks','objects','actions'): raise ValueError('Неизвестный раздел')
    db.execute('BEGIN IMMEDIATE')
    old=db.execute('SELECT actor FROM saved_views WHERE id=?',(vid,)).fetchone()
    if old and old[0]!=user: raise Conflict()
    if not old and db.execute('SELECT COUNT(*) FROM saved_views WHERE actor=?',(user,)).fetchone()[0]>=30: raise ValueError('Можно сохранить до 30 видов')
    db.execute('INSERT INTO saved_views VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,filters=excluded.filters',(vid,user,name,json.dumps(filters,ensure_ascii=False)))
