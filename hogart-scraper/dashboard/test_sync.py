"""12.11: the dashboard snapshot made 98% of Megaplan calls and timed out on invoice pages."""
import json
import tempfile
import time
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path

import sync


class FakeApi:
    def __init__(self, failures=0, rows=7):
        self.failures, self.rows, self.calls = failures, rows, []

    def _call(self, method, endpoint, params=None):
        self.calls.append(dict(params or {}))
        if self.failures:
            self.failures -= 1
            raise TimeoutError('slow page')
        after = int((params.get('pageAfter') or {}).get('id', 0))
        size = params['limit']
        chunk = [{'id': i} for i in range(after + 1, min(after + size, self.rows) + 1)]
        return {'data': chunk, 'meta': {'pagination': {'hasMoreNext': chunk[-1]['id'] < self.rows,
                                                       'count': self.rows}}}


class SyncTests(unittest.TestCase):
    def test_slow_page_is_retried_smaller_with_the_same_cursor(self):
        api = FakeApi(failures=2, rows=30)
        rows = sync.fetch(api, '/invoice', 'Invoice', ['sum'], sleep=lambda s: None)
        self.assertEqual(30, len(rows))
        self.assertEqual([100, 50, 25], [c['limit'] for c in api.calls[:3]], 'та же страница, меньший размер')

    def test_page_that_never_answers_fails_the_snapshot_not_silently(self):
        with self.assertRaises(TimeoutError):
            sync.fetch(FakeApi(failures=3), '/invoice', 'Invoice', [], sleep=lambda s: None)

    def test_full_snapshot_at_most_once_an_hour(self):
        with tempfile.TemporaryDirectory() as folder:
            data = Path(folder)
            self.assertTrue(sync.due(data), 'снимка ещё не было')
            done = datetime.now(timezone.utc) - timedelta(minutes=20)
            (data / 'sync-status.json').write_text(json.dumps({'ok': True, 'completed_at': done.isoformat()}))
            self.assertFalse(sync.due(data), '20 минут назад — Мегаплан не запрашиваем')
            old = datetime.now(timezone.utc) - timedelta(minutes=61)
            (data / 'sync-status.json').write_text(json.dumps({'ok': True, 'completed_at': old.isoformat()}))
            self.assertTrue(sync.due(data))

    def test_failed_attempt_does_not_count_as_a_snapshot(self):
        with tempfile.TemporaryDirectory() as folder:
            data = Path(folder)
            done = datetime.now(timezone.utc) - timedelta(minutes=70)
            (data / 'sync-status.json').write_text(json.dumps({'ok': False, 'attempted_at': datetime.now(timezone.utc).isoformat(),
                                                               'completed_at': done.isoformat()}))
            self.assertTrue(sync.due(data))

    def test_owner_request_forces_a_snapshot(self):
        with tempfile.TemporaryDirectory() as folder:
            data = Path(folder)
            (data / 'sync-status.json').write_text(json.dumps({'ok': True, 'completed_at': datetime.now(timezone.utc).isoformat()}))
            (data / 'sync-request').write_text('')
            self.assertTrue(sync.due(data))


if __name__ == '__main__':
    unittest.main()
