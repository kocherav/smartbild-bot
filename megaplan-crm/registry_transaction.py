"""Reentrant process/thread locking around an entire JSON read-modify-write."""
from contextlib import contextmanager
from functools import wraps
import fcntl
import os
from pathlib import Path
import threading

_local=threading.local()
_locks={}
_guard=threading.Lock()


@contextmanager
def locked(path):
    path=str(Path(path).resolve())
    with _guard:
        lock=_locks.setdefault(path,threading.RLock())
    with lock:
        active=getattr(_local,'active',set())
        if path in active:
            yield; return
        with open(path+'.lock','a') as file:
            os.chmod(path+'.lock',0o600)
            fcntl.flock(file,fcntl.LOCK_EX)
            _local.active=active|{path}
            try: yield
            finally: _local.active=active


def transaction(path_getter):
    def decorate(fn):
        @wraps(fn)
        def wrapped(*args,**kwargs):
            with locked(path_getter()):
                return fn(*args,**kwargs)
        return wrapped
    return decorate
