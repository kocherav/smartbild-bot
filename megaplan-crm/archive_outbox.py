"""Durable archive delivery; contains no financial-operation writer."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
import time
from registry_transaction import locked

ROOT=Path(__file__).resolve().parent/'archive_outbox'


def connect():
    ROOT.mkdir(mode=0o700,exist_ok=True)
    db=sqlite3.connect(ROOT/'jobs.sqlite3',timeout=10); db.row_factory=sqlite3.Row
    db.execute('''CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,payload TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending',attempts INTEGER NOT NULL DEFAULT 0,
        updated REAL NOT NULL,error TEXT,receipt TEXT)''')
    os.chmod(ROOT/'jobs.sqlite3',0o600)
    return db


def enqueue(spec):
    from financial_archive import CATEGORIES,sha256
    path=Path(spec['path']); category=spec['category']
    if category not in CATEGORIES or not path.is_file(): raise ValueError('Некорректный файл или категория архива')
    digest=sha256(path); deal_id=str(spec['deal_id'])
    key=hashlib.sha256(f'{deal_id}|{category}|{digest}'.encode()).hexdigest()
    db=connect()
    try:
        old=db.execute('SELECT * FROM jobs WHERE id=?',(key,)).fetchone()
        if old:
            if old['status']=='done': return json.loads(old['receipt'])
            return {'ok':False,'queued':True,'archive_job_id':key,'error':'Исходник сохранён. Загрузка в OneDrive ожидает фоновой обработки.'}
        target=ROOT/(digest+path.suffix.lower())
        if not target.exists():
            fd,tmp=tempfile.mkstemp(prefix='.source-',dir=ROOT); os.close(fd)
            try:
                shutil.copyfile(path,tmp); os.chmod(tmp,0o600)
                if sha256(tmp)!=digest: raise ValueError('Исходный файл изменился во время сохранения')
                with open(tmp,'rb') as saved: os.fsync(saved.fileno())
                os.replace(tmp,target)
            finally:
                if os.path.exists(tmp): os.unlink(tmp)
        payload={'deal_id':deal_id,'category':category,'path':str(target),
                 'document_number':str(spec.get('document_number') or ''),
                 'display_name':spec.get('display_name') or path.name}
        db.execute('INSERT OR IGNORE INTO jobs(id,payload,updated) VALUES(?,?,?)',(key,json.dumps(payload,ensure_ascii=False),time.time())); db.commit()
        return {'ok':False,'queued':True,'archive_job_id':key,'error':'Исходник сохранён. Загрузка в OneDrive поставлена в фоновую очередь.'}
    finally: db.close()


def drain(limit=1):
    from financial_archive import archive_document
    connect().close()
    with locked(str(ROOT/'worker')):
        db=connect()
        # Only derivative file delivery can replay after process interruption.
        jobs=db.execute("SELECT * FROM jobs WHERE status!='done' AND (error IS NULL OR updated<?) ORDER BY updated LIMIT ?",(time.time()-300,max(1,min(int(limit),5)))).fetchall(); db.close()
        results=[]
        for job in jobs:
            try:
                result=archive_document(**json.loads(job['payload']))
                if not result.get('ok'): raise ValueError('Archive did not confirm delivery')
                status,error='done',None
            except Exception as exc:
                result={}; status,error='pending',type(exc).__name__
            db=connect(); db.execute('UPDATE jobs SET status=?,error=?,receipt=?,attempts=attempts+1,updated=? WHERE id=?',
                (status,error,json.dumps(result,ensure_ascii=False),time.time(),job['id'])); db.commit(); db.close()
            results.append({'id':job['id'],'status':status,'error':error})
        return {'ok':True,'jobs':results}


if __name__=='__main__':
    try:
        spec=json.load(sys.stdin)
        result=drain(spec.get('limit',1)) if spec.get('action')=='drain' else enqueue(spec)
        print(json.dumps(result,ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({'ok':False,'error':type(exc).__name__},ensure_ascii=False)); sys.exit(1)
