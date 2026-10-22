import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
from workflow_runtime import Store
from effect_runner import execute


class EffectsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.db = Store(Path(self.temp.name) / 'effects.sqlite3')

    def run_action(self, action, **kw):
        return execute(self.db, 'owner', 'create_invoice', 'confirmed-preview', {'deal_id': 'demo'}, {'sum': '100'}, action, **kw)

    def test_retry_reuses_receipt(self):
        action = Mock(return_value={'ok': True, 'id': 'invoice'})
        a, b = self.run_action(action), self.run_action(action)
        self.assertEqual(a['id'], b['id']); self.assertTrue(b['_reused'])
        action.assert_called_once()

    def test_timeout_never_repeats_external_write(self):
        action = Mock(side_effect=TimeoutError('potential secret'))
        self.assertTrue(self.run_action(action)['uncertain'])
        self.assertTrue(self.run_action(action)['uncertain'])
        action.assert_called_once()
        self.assertNotIn('potential secret', str(self.db.get(self.run_action(action)['_operation_id'])))

    def test_old_context_never_calls_action(self):
        action = Mock()
        self.assertTrue(self.run_action(action, fresh=lambda: False)['stale'])
        action.assert_not_called()

    def test_verified_remote_success_recovers_receipt_without_replaying(self):
        action=Mock(side_effect=TimeoutError())
        first=self.run_action(action); op=self.db.get(first['_operation_id'])
        self.db.reconcile(op['id'],op['revision'],'operator','succeeded','Read external invoice ID verified',{'ok':True,'id':'verified'})
        self.assertEqual('verified',self.run_action(action)['id'])
        action.assert_called_once()

    def test_no_effect_resolution_does_not_replay_automatically(self):
        action=Mock(side_effect=TimeoutError())
        first=self.run_action(action); op=self.db.get(first['_operation_id'])
        self.db.reconcile(op['id'],op['revision'],'operator','failed','Authoritative remote log checked; request rejected')
        self.assertFalse(self.run_action(action)['ok']); action.assert_called_once()

    def test_running_operation_cannot_be_reconciled(self):
        op=self.db.create('owner','write','key',{},{}); self.db.confirm(op['id'],1); self.db.claim(op['id'])
        with self.assertRaises(ValueError):
            self.db.reconcile(op['id'],1,'operator','failed','not enough to stop active worker')

    def test_new_preview_allows_deliberate_new_operation(self):
        action = Mock(return_value={'ok': True})
        self.run_action(action)
        execute(self.db, 'owner', 'create_invoice', 'new-preview', {'deal_id': 'demo'}, {'sum': '100'}, action)
        self.assertEqual(2, action.call_count)

    def test_new_preview_cannot_bypass_unresolved_remote_write(self):
        first=Mock(side_effect=TimeoutError()); self.run_action(first)
        second=Mock(return_value={'ok':True})
        result=execute(self.db,'owner','create_invoice','new-preview',{'deal_id':'demo'},{'sum':'100'},second)
        self.assertTrue(result['no_effect']); second.assert_not_called()

if __name__ == '__main__':
    unittest.main()
