import json
from pathlib import Path
import tempfile
import unittest
from ui_context import StateStore


class ContextTests(unittest.TestCase):
    def test_background_transition_cannot_claim_busy_or_changed_context(self):
        context=self.store.bind('a','1')
        self.store.update('a',{'pending':'invoice_file'},context)
        self.assertIsNone(self.store.begin_idle('a',context.revision,{'current_deal_id':'new'}))
        self.store.update('a',{'pending':None},context)
        old=context.revision;self.store.bind('a','2')
        self.assertIsNone(self.store.begin_idle('a',old,{'current_deal_id':'new'}))

    def test_claimed_background_is_stale_after_next_user_input(self):
        context=self.store.begin_idle('a',0,{'current_deal_id':'one','pending':'procurement_stock_confirm'})
        self.assertIsNotNone(context)
        self.assertTrue(context.state.get('_confirmation_id'))
        newer=self.store.bind('a','1');self.store.update('a',{'current_deal_id':'two'},newer)
        ok,_=self.store.update('a',{'current_deal_id':'one'},context)
        self.assertFalse(ok)
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'state.json'
        self.store = StateStore(self.path, self.path.with_suffix('.lock'))

    def test_old_worker_cannot_replace_new_deal(self):
        first = self.store.bind('a', '1')
        self.store.update('a', {'current_deal_id': 'one'}, first)
        second = self.store.bind('a', '2')
        self.store.update('a', {'current_deal_id': 'two'}, second)
        ok, _ = self.store.update('a', {'current_deal_id': 'one', 'pending': 'invoice_file'}, first)
        self.assertFalse(ok)
        self.assertEqual('two', self.store.current('a')['current_deal_id'])
        self.assertFalse(self.store.fresh(first))

    def test_worker_reads_original_snapshot_not_new_selection(self):
        self.store.update('a', {'current_deal_id': 'one'})
        context = self.store.bind('a', '1')
        self.store.update('a', {'current_deal_id': 'two'})
        self.assertEqual('one', self.store.current('a', context)['current_deal_id'])

    def test_consecutive_updates_by_same_worker_are_allowed(self):
        context = self.store.bind('a', '1')
        for i in range(4):
            self.assertTrue(self.store.update('a', {'value': i}, context)[0])
        self.assertTrue(self.store.fresh(context))

    def test_unrelated_actor_does_not_invalidate_context(self):
        context = self.store.bind('a', '1')
        self.store.bind('b', '1')
        self.assertTrue(self.store.fresh(context))

    def test_duplicate_update_is_not_bound_twice(self):
        self.store.bind('a', '1')
        self.assertIsNone(self.store.bind('a', '1'))

    def test_broken_state_is_not_silently_replaced(self):
        self.path.write_text('{broken', encoding='utf-8')
        with self.assertRaises(json.JSONDecodeError):
            self.store.bind('a', '1')
        self.assertEqual('{broken', self.path.read_text())

    def test_legacy_state_is_preserved_and_none_removes(self):
        self.path.write_text('{"a":{"current_deal_id":"one","pending":"old"}}', encoding='utf-8')
        context = self.store.bind('a', '1')
        self.store.update('a', {'pending': None}, context)
        self.assertEqual('one', self.store.current('a')['current_deal_id'])
        self.assertNotIn('pending', self.store.current('a'))

    def test_late_invoice_is_queued_without_switching_deal(self):
        first = self.store.bind('a', '1')
        second = self.store.bind('a', '2')
        self.store.update('a', {'current_deal_id': 'two', 'pending': 'contract_date'}, second)
        self.store.invoice_queue('a', {'deal_id': 'one', 'invoice': {'number': 'A'}}, context=first)
        state = self.store.current('a')
        self.assertEqual('two', state['current_deal_id'])
        self.assertEqual('contract_date', state['pending'])
        self.assertEqual(1, len(state['supplier_invoice_queue']))

    def test_two_invoices_display_queue_head_and_never_mix(self):
        context = self.store.bind('a', '1')
        one, two = {'deal_id': 'one', 'invoice': {'number': 'A'}}, {'deal_id': 'two', 'invoice': {'number': 'B'}}
        self.store.invoice_queue('a', one, context=context)
        self.store.invoice_queue('a', two, context=context)
        state = self.store.current('a', context)
        self.assertEqual('one', state['current_deal_id'])
        self.assertEqual(one, state['supplier_invoice_preview'])
        self.store.invoice_queue('a', one, remove=True, context=context)
        self.assertEqual(two, self.store.current('a', context)['supplier_invoice_preview'])

if __name__ == '__main__':
    unittest.main()
