import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
from workflow_runtime import Store
import decision_channel as channel


class DecisionChannelTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.store = Store(Path(self.tmp.name) / 'questions.sqlite3')
        self.sender = Mock(return_value={'ok': True, 'result': {'message_id': 42}})

    def message(self, text='Да', reply=42):
        return {'chat': {'id': 10}, 'from': {'id': 10}, 'message_id': 50,
                'text': text, 'reply_to_message': {'message_id': reply}}

    def test_delivery_then_reply_is_captured(self):
        channel.ask(self.store, '10', 'Q-ONE', 'A4', 'Нужен выбор', self.sender)
        saved = channel.consume(self.message(), '10', self.store)
        self.assertEqual('Да', saved['answer'])

    def test_non_question_reply_is_not_consumed(self):
        self.assertIsNone(channel.consume(self.message(), '10', self.store))

    def test_other_user_cannot_answer_by_code(self):
        channel.ask(self.store, '10', 'Q-ONE', 'A4', 'Выбор', self.sender)
        msg = self.message('Q-ONE: Да'); msg['from']['id'] = 11
        self.assertIsNone(channel.consume(msg, '10', self.store))

    def test_explicit_code_is_accepted_without_reply(self):
        channel.ask(self.store, '10', 'Q-ONE', 'A4', 'Выбор', self.sender)
        self.assertEqual('нет', channel.consume(self.message('Q-ONE: нет', None), '10', self.store)['answer'])

    def test_retry_does_not_send_question_again(self):
        for _ in range(2):
            channel.ask(self.store, '10', 'Q-ONE', 'A4', 'Выбор', self.sender)
        self.sender.assert_called_once()

    def test_failed_delivery_does_not_claim_sent(self):
        with self.assertRaises(RuntimeError):
            channel.ask(self.store, '10', 'Q-ONE', 'A4', 'Выбор', lambda _: {'ok': False})
        self.assertEqual('prepared', self.store.questions('10')[0]['status'])

if __name__ == '__main__':
    unittest.main()
