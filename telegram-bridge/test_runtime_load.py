"""Local contention/load checks. No Telegram, model, CRM or supplier requests."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import bridge
from workflow_runtime import Store
from effect_runner import execute


class LoadTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup); self.root=Path(tmp.name)

    def test_twenty_competing_confirmations_dispatch_one_write(self):
        store=Store(self.root/'runtime.sqlite3'); count=0; lock=threading.Lock()
        def action():
            nonlocal count
            with lock: count+=1
            return {'ok':True,'id':'one-receipt'}
        def attempt(_):
            return execute(store,'owner','create','same-preview',{'deal_id':'demo'},{'total':100},action)
        with ThreadPoolExecutor(max_workers=8) as pool: results=list(pool.map(attempt,range(20)))
        self.assertEqual(1,count); self.assertTrue(any(x.get('ok') for x in results))
        self.assertEqual('one-receipt',attempt(None)['id'])

    def test_local_navigation_does_not_call_business_api_or_model(self):
        with (patch.multiple(bridge,RUNTIME_ACTIVE=True,UI_CONTEXT=None,
                            DEAL_UI_STATE_FILE=str(self.root/'state.json'),DEAL_UI_STATE_LOCK_FILE=str(self.root/'state.lock'),
                            WORKFLOW_DB_FILE=str(self.root/'runtime.sqlite3')),
             patch.object(bridge,'tg_api',return_value={'ok':True}),
             patch.object(bridge,'run_deal_browser',side_effect=AssertionError('Menu called CRM')),
             patch.object(bridge,'ask_fresh_document_model',side_effect=AssertionError('Menu called model'))):
            times=[]
            for i in range(100):
                start=time.monotonic()
                bridge.UI_CONTEXT=bridge.ui_state_store().bind('owner',str(i))
                self.assertTrue(bridge.handle_global_navigation('fake','owner','🤝 Сделки'))
                times.append(time.monotonic()-start)
        p95=sorted(times)[94]
        print(f'LOCAL_MENU_BENCHMARK count=100 p95_ms={p95*1000:.2f} max_ms={max(times)*1000:.2f}')
        self.assertLess(p95,0.5,'Local menu unexpectedly blocked')

    def test_inactive_inline_view_history_is_bounded(self):
        store=Store(self.root/'runtime.sqlite3')
        for index in range(80):
            store.keyboard('owner',[[{'text':f'action-{index}'}]])
        with store.connect() as db:
            self.assertLessEqual(db.execute("SELECT count(*) FROM views WHERE actor='owner'").fetchone()[0],51)
            self.assertLessEqual(db.execute('SELECT count(*) FROM controls').fetchone()[0],51)


if __name__=='__main__': unittest.main()
