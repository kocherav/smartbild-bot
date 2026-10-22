import tempfile
from pathlib import Path
import unittest
from unittest.mock import Mock
from workflow_runtime import Store
from delivery_steps import deliver


class DeliveryTest(unittest.TestCase):
    def test_changed_bundle_never_mixes_versions_on_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            store=Store(Path(directory)/'operations.sqlite3')
            action=Mock(return_value=True)
            self.assertTrue(deliver(store,'bundle','version1',[('email',action)])['ok'])
            self.assertFalse(deliver(store,'bundle','version2',[('email',action)])['ok'])
            self.assertEqual(1,action.call_count)
            self.assertTrue(deliver(store,'explicit-new-bundle','version2',[('email',action)])['ok'])
    def test_successful_channel_not_repeated_after_partial_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / 'operations.sqlite3')
            mail, tg = Mock(return_value=True), Mock(side_effect=TimeoutError)
            first = deliver(store, 'invoice-7', 'hash', [('email', mail), ('telegram', tg)])
            second = deliver(store, 'invoice-7', 'hash', [('email', mail), ('telegram', tg)])
            self.assertFalse(first['ok']); self.assertFalse(second['ok'])
            mail.assert_called_once(); tg.assert_called_once()

    def test_duplicate_completed_bundle_reuses_receipts(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / 'operations.sqlite3'); action = Mock(return_value=True)
            for _ in range(2): self.assertTrue(deliver(store, 'bundle', 'hash', [('email', action)])['ok'])
            action.assert_called_once()


if __name__ == '__main__': unittest.main()
