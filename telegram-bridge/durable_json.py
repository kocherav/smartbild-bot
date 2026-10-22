"""Small fail-closed storage for legacy ledgers while their readers coexist."""
from contextlib import contextmanager
from functools import wraps
import fcntl
import json
import os
import tempfile
import threading

_guard=threading.Lock()
_locks={}
_local=threading.local()

@contextmanager
def locked(path):
    path=os.path.realpath(path)
    with _guard: lock=_locks.setdefault(path,threading.RLock())
    with lock:
        active=getattr(_local,'active',set())
        if path in active:
            yield
            return
        with open(path+'.lock','a') as stream:
            os.chmod(path+'.lock',0o600)
            fcntl.flock(stream,fcntl.LOCK_EX)
            _local.active=active|{path}
            try: yield
            finally: _local.active=active

def transaction(path):
    def decorate(fn):
        @wraps(fn)
        def call(*args,**kwargs):
            with locked(path()): return fn(*args,**kwargs)
        return call
    return decorate

def read(path,default):
    try:
        with open(path,encoding='utf-8') as stream:
            result=json.load(stream,parse_constant=lambda value: (_ for _ in ()).throw(ValueError('Неконечное число в реестре')))
    except FileNotFoundError:
        return default()
    if not isinstance(result,dict): raise ValueError('Некорректная структура реестра')
    return result

def save(path,data):
    # Serialization precedes replacement; invalid numeric values never replace
    # a valid financial history. The caller locks the entire read/modify/write.
    encoded=json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False)
    fd,tmp=tempfile.mkstemp(prefix='.ledger-',dir=os.path.dirname(os.path.abspath(path)))
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as stream:
            stream.write(encoded); stream.flush(); os.fsync(stream.fileno())
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)
