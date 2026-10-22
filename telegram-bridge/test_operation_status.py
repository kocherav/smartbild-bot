import unittest
from unittest.mock import patch,Mock
import bridge

class StatusTests(unittest.TestCase):
    def test_status_is_observation_not_navigation_or_retry(self):
        with (patch.object(bridge,'WorkflowStore') as store,
              patch.object(bridge,'latest_processing_document_job',return_value={'stage':'сопоставление'}),
              patch.object(bridge,'latest_retryable_document_job',return_value=None),
              patch.object(bridge,'send_message') as send,
              patch.object(bridge,'update_deal_ui_state') as update):
            store.return_value.unresolved.return_value=[{'id':'op1','scenario':'invoice',
                'status':'uncertain','target':{'deal_id':'861'}}]
            self.assertTrue(bridge.handle_status_query('token','owner','Что сейчас делает бот?'))
            update.assert_not_called()
            self.assertIn('сверка',send.call_args.args[2])
            self.assertIn('861',send.call_args.args[2])
            self.assertIn('сопоставление',send.call_args.args[2])
            store.return_value.unresolved.assert_called_once_with('owner')

    def test_other_messages_are_not_consumed(self):
        with patch.object(bridge,'WorkflowStore') as store:
            self.assertFalse(bridge.handle_status_query('token','owner','создать счёт'))
            store.assert_not_called()

    def test_unreadable_journal_is_not_reported_as_idle(self):
        with patch.object(bridge,'WorkflowStore',side_effect=ValueError('corrupt')),patch.object(bridge,'send_message') as send:
            self.assertTrue(bridge.handle_status_query('token','owner','/status'))
            self.assertIn('Не удалось прочитать',send.call_args.args[2])

if __name__=='__main__':unittest.main()
