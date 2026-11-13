"""Read-only Megaplan snapshot. Publish only complete paginated collections."""
import fcntl
import json
import os
from pathlib import Path
import sys
import time
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent
CRM = Path('/home/kocher.av/megaplan-crm')
sys.path.insert(0, str(CRM))
from megaplan_api import MegaplanAPI
from megaplan_transport import ProtectionPause

# 12.11 (TASK-20261112-03): this snapshot made 97.9% of all Megaplan calls — every
# 10 minutes it re-read every deal and invoice page with nested finance operations, and
# heavy invoice pages timed out (the owner's «TimeoutError» notices). The systemd timer
# still fires every 10 minutes; the script itself now decides what is really needed.
FULL_INTERVAL = 3600        # a full snapshot at most once an hour
PROGRAMS_INTERVAL = 86400   # program schemas change rarely
PAGE_SIZES = (100, 50, 25)  # a page that does not answer is retried smaller (reads only)
TRANSIENT = (TimeoutError, OSError)


def atomic(path, value):
    tmp = path.with_suffix('.tmp')
    with tmp.open('w') as f:
        json.dump(value, f, ensure_ascii=False, allow_nan=False)
    tmp.chmod(0o660)
    tmp.replace(path)


def fetch(api, endpoint, content_type, fields, sleep=time.sleep):
    rows, seen = [], set()
    params = {'limit': PAGE_SIZES[0], 'fields': fields}
    for _ in range(400):
        pauses = 0
        for size in PAGE_SIZES:
            params['limit'] = size
            try:
                result = api._call('GET', endpoint, params=params)
                break
            except ProtectionPause:
                pauses += 1
                if pauses > 3: raise
                sleep(15)
            except TRANSIENT:
                # The same cursor, a smaller page: safe for a read, and a heavy page of
                # invoices with nested finance operations answers within the timeout.
                if size == PAGE_SIZES[-1]: raise
                sleep(20)
        else:
            raise ValueError('Page not read: ' + endpoint)
        chunk = result.get('data')
        if not isinstance(chunk, list): raise ValueError('Invalid collection: ' + endpoint)
        for row in chunk:
            key = str(row['id'])
            if key in seen: raise ValueError('Repeated page: ' + endpoint)
            seen.add(key)
        rows.extend(chunk)
        more = result.get('meta', {}).get('pagination', {}).get('hasMoreNext')
        if not more:
            expected = result.get('meta', {}).get('pagination', {}).get('count')
            if expected is not None and int(expected) != len(rows):
                raise ValueError('Collection changed during read: ' + endpoint)
            return rows
        if not chunk: raise ValueError('Empty intermediate page')
        params['pageAfter'] = {'contentType': content_type, 'id': chunk[-1]['id']}
    raise ValueError('Pagination limit reached')


def _read(path):
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, ValueError):
        return {}


def _age(stamp, now):
    try:
        return now - datetime.fromisoformat(stamp).timestamp()
    except (TypeError, ValueError):
        return float('inf')


def due(data, now=None):
    """A full snapshot is needed if the last successful one is older than FULL_INTERVAL
    or the owner asked for a refresh (``data/sync-request``)."""
    now = time.time() if now is None else now
    if (data / 'sync-request').exists():
        return True
    return _age(_read(data / 'sync-status.json').get('completed_at'), now) >= FULL_INTERVAL


def main():
    os.environ['MEGAPLAN_PRIORITY'] = 'background'
    data = ROOT / 'data'
    data.mkdir(exist_ok=True)
    with (data / 'sync.lock').open('w') as lock:
        try: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: return
        if not due(data):
            print('Snapshot is fresh; Megaplan not queried', flush=True)
            return
        started = datetime.now(timezone.utc).isoformat()
        try:
            api = MegaplanAPI()
            deals = fetch(api, '/deal', 'Deal', ['state', 'result', 'program', 'manager', 'contractor',
                'price', 'positionsCount', 'timeCreated', 'timeUpdated', 'financeOperations',
                'financeOperationsCount', 'invoices', 'Category1000068CustomFieldAdresObEkta',
                'Category1000068CustomFieldIspolnitel'])
            print('Deals fetched:', len(deals), flush=True)
            invoices = fetch(api, '/invoice', 'Invoice', ['deal', 'sum', 'financeOperations',
                'financeOperationsCount', 'status', 'invoiceDate', 'recipient'])
            print('Invoices fetched:', len(invoices), flush=True)
            previous = _read(data / 'crm.json')
            wanted = sorted({str((d.get('program') or {})['id']) for d in deals if (d.get('program') or {}).get('id')})
            cached = {str(p.get('id')): p for p in previous.get('programs') or []}
            fresh = _age(previous.get('programs_at'), time.time()) < PROGRAMS_INTERVAL
            if fresh and set(wanted) <= set(cached):
                programs, programs_at = [cached[i] for i in wanted], previous['programs_at']
            else:
                programs = [api._call('GET', '/program/' + ident)['data'] for ident in wanted]
                programs_at = datetime.now(timezone.utc).isoformat()
            now = datetime.now(timezone.utc).isoformat()
            atomic(data / 'crm.json', {'synced_at': now, 'deals': deals, 'invoices': invoices,
                'programs': programs, 'programs_at': programs_at, 'domain': api.domain})
            try:
                (data / 'sync-request').unlink()
            except FileNotFoundError:
                pass
            atomic(data / 'sync-status.json', {'ok': True, 'attempted_at': started, 'completed_at': now})
            print('Snapshot published', now, flush=True)
        except Exception as exc:
            # Do not log request URLs, auth state, or upstream response bodies.
            atomic(data / 'sync-status.json', {'ok': False, 'attempted_at': started,
                'error': type(exc).__name__})
            print('Snapshot preserved. Sync failed:', type(exc).__name__, flush=True)
            raise SystemExit(1)

if __name__ == '__main__': main()
