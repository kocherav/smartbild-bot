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


def atomic(path, value):
    tmp = path.with_suffix('.tmp')
    with tmp.open('w') as f:
        json.dump(value, f, ensure_ascii=False, allow_nan=False)
    tmp.chmod(0o660)
    tmp.replace(path)


def fetch(api, endpoint, content_type, fields):
    rows, seen = [], set()
    params = {'limit': 100, 'fields': fields}
    for _ in range(100):
        for attempt in range(4):
            try:
                result = api._call('GET', endpoint, params=params)
                break
            except ProtectionPause:
                if attempt == 3: raise
                time.sleep(15)
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


def main():
    os.environ['MEGAPLAN_PRIORITY'] = 'background'
    data = ROOT / 'data'
    data.mkdir(exist_ok=True)
    with (data / 'sync.lock').open('w') as lock:
        try: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: return
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
            programs = []
            for ident in sorted({str((d.get('program') or {})['id']) for d in deals if (d.get('program') or {}).get('id')}):
                programs.append(api._call('GET', '/program/' + ident)['data'])
            now = datetime.now(timezone.utc).isoformat()
            atomic(data / 'crm.json', {'synced_at': now, 'deals': deals, 'invoices': invoices,
                'programs': programs, 'domain': api.domain})
            atomic(data / 'sync-status.json', {'ok': True, 'attempted_at': started, 'completed_at': now})
            print('Snapshot published', now, flush=True)
        except Exception as exc:
            # Do not log request URLs, auth state, or upstream response bodies.
            atomic(data / 'sync-status.json', {'ok': False, 'attempted_at': started,
                'error': type(exc).__name__})
            print('Snapshot preserved. Sync failed:', type(exc).__name__, flush=True)
            raise SystemExit(1)

if __name__ == '__main__': main()
