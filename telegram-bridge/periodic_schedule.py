"""Persistent rate gate for read-only watchers, including process restarts."""
import math
import time
import durable_json
from datetime import datetime, timezone

def claim(path,key,interval,now=None,delay_first=False):
    current=time.time() if now is None else float(now)
    interval=float(interval)
    if not math.isfinite(current) or not math.isfinite(interval) or interval<=0:
        raise ValueError('Invalid watcher interval')
    @durable_json.transaction(lambda:path)
    def check():
        schedule=durable_json.read(path,dict)
        previous=schedule.get(key)
        if previous is not None:
            previous=float(previous)
            if not math.isfinite(previous):raise ValueError('Invalid watcher timestamp')
            if current-previous<interval:return False
        schedule[key]=current
        durable_json.save(path,schedule)
        return not (previous is None and delay_first)
    return check()

def claim_daily(path,key,hour_utc,now=None):
    moment=datetime.now(timezone.utc) if now is None else now
    if moment.tzinfo is None:raise ValueError('Daily schedule requires timezone-aware datetime')
    moment=moment.astimezone(timezone.utc);hour_utc=int(hour_utc)
    if not 0<=hour_utc<=23 or moment.hour<hour_utc:return False
    day=moment.date().isoformat()
    @durable_json.transaction(lambda:path)
    def check():
        schedule=durable_json.read(path,dict)
        if schedule.get(key)==day:return False
        schedule[key]=day;durable_json.save(path,schedule);return True
    return check()
