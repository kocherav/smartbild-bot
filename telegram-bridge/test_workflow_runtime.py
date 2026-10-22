import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from workflow_runtime import Store, Conflict


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'runtime.sqlite3'
        self.db = Store(self.path)

    def operation(self, key='one'):
        return self.db.create('owner', 'invoice', key, {'deal_id': 'test-deal'}, {'amount': '100.00'})

    def test_same_key_same_operation(self):
        first = self.operation()
        self.assertEqual(first['id'], self.operation()['id'])

    def test_key_cannot_change_payload_or_target(self):
        self.operation()
        with self.assertRaises(Conflict):
            self.db.create('owner', 'invoice', 'one', {'deal_id': 'other'}, {'amount': '100.00'})

    def test_stale_confirmation_is_rejected(self):
        op = self.operation()
        changed = self.db.revise(op['id'], op['revision'], {'amount': '200.00'})
        with self.assertRaises(Conflict):
            self.db.confirm(op['id'], op['revision'])
        self.assertEqual('draft', changed['status'])

    def test_confirmation_binds_payload(self):
        op = self.operation()
        self.db.confirm(op['id'], op['revision'])
        with self.assertRaises(Conflict):
            self.db.revise(op['id'], op['revision'], {'amount': '999.00'})

    def test_only_one_concurrent_claim(self):
        op = self.operation()
        self.db.confirm(op['id'], op['revision'])
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: Store(self.path).claim(op['id']), range(4)))
        self.assertEqual(1, sum(x is not None for x in results))

    def test_cannot_claim_unconfirmed_or_cancelled(self):
        op = self.operation()
        self.assertIsNone(self.db.claim(op['id']))
        self.db.cancel(op['id'])
        with self.assertRaises(Conflict):
            self.db.confirm(op['id'], op['revision'])

    def test_completed_receipt_survives_restart(self):
        op = self.operation()
        self.db.confirm(op['id'], op['revision'])
        self.db.claim(op['id'])
        self.db.finish(op['id'], {'ok': True, 'id': 'remote-id'})
        restored = Store(self.path).get(op['id'])
        self.assertEqual('succeeded', restored['status'])
        self.assertEqual('remote-id', restored['receipt']['id'])
        self.assertIsNone(self.db.claim(op['id']))

    def test_interrupted_external_write_is_uncertain_not_retried(self):
        op = self.operation()
        self.db.confirm(op['id'], op['revision'])
        self.db.claim(op['id'])
        self.db.recover()
        self.assertEqual('uncertain', self.db.get(op['id'])['status'])
        self.assertIsNone(self.db.claim(op['id']))

    def test_cancel_does_not_undo_running_write(self):
        op = self.operation()
        self.db.confirm(op['id'], op['revision'])
        self.db.claim(op['id'])
        with self.assertRaises(Conflict):
            self.db.cancel(op['id'])

    def test_duplicate_updates_are_atomic(self):
        self.assertTrue(self.db.receive('owner', '100', {'kind': 'text'}))
        self.assertFalse(self.db.receive('owner', '100', {'kind': 'text'}))
        self.assertTrue(self.db.receive('other', '100', {'kind': 'text'}))

    def test_questions_bind_owner_and_telegram_reply(self):
        q = self.db.question('owner', 'Q-1', 'Нужен выбор', 'A6')
        self.db.question_sent(q['id'], 901)
        self.assertIsNone(self.db.answer('stranger', 901, 'yes', '1'))
        a = self.db.answer('owner', 901, 'Вариант 2', '2')
        self.assertEqual(q['id'], a['id'])
        self.assertEqual('Вариант 2', a['answer'])
        self.assertEqual('answered', a['status'])

    def test_duplicate_question_delivery_and_answer(self):
        q = self.db.question('owner', 'Q-1', 'Нужен выбор', 'A6')
        self.assertEqual(q['id'], self.db.question('owner', 'Q-1', 'Нужен выбор', 'A6')['id'])
        self.db.question_sent(q['id'], 901)
        self.db.answer('owner', 901, 'yes', '2')
        self.db.answer('owner', 901, 'yes', '2')
        self.assertEqual(1, len(self.db.question_answers(q['id'])))

    def test_textual_question_code_and_correction_keep_history(self):
        q = self.db.question('owner', 'Q-2', 'Нужен выбор', 'A6')
        self.db.answer('owner', None, 'yes', '2', code='Q-2')
        self.db.answer('owner', None, 'no', '3', code='Q-2')
        self.assertEqual(2, len(self.db.question_answers(q['id'])))
        self.assertEqual('no', self.db.questions('owner')[0]['answer'])

    def test_json_rejects_nonfinite_amount(self):
        with self.assertRaises(ValueError):
            self.db.create('owner', 'invoice', 'nan', {}, {'amount': float('nan')})

    def test_callback_belongs_to_owner_and_current_view(self):
        keyboard = self.db.keyboard('owner', [[{'text': 'Применить'}]])
        token = keyboard['inline_keyboard'][0][0]['callback_data'][3:]
        self.assertFalse(self.db.take_control('other', token)['ok'])
        self.assertEqual('Применить', self.db.take_control('owner', token)['text'])
        self.assertEqual('already_used', self.db.take_control('owner', token)['reason'])

    def test_old_callback_does_not_apply_to_next_invoice(self):
        old = self.db.keyboard('owner', [[{'text': 'Применить'}]])
        self.db.keyboard('owner', [[{'text': 'Применить'}]])
        token = old['inline_keyboard'][0][0]['callback_data'][3:]
        self.assertEqual('expired', self.db.take_control('owner', token)['reason'])

    def test_two_choices_of_one_preview_cannot_both_execute(self):
        keyboard = self.db.keyboard('owner', [[{'text': 'В сделку'}, {'text': 'В остатки'}]])
        tokens = [b['callback_data'][3:] for b in keyboard['inline_keyboard'][0]]
        self.assertTrue(self.db.take_control('owner', tokens[0])['ok'])
        self.assertFalse(self.db.take_control('owner', tokens[1])['ok'])

if __name__ == '__main__':
    unittest.main()
