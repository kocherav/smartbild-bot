import unittest
from unittest.mock import Mock

import megaplan_transport
from megaplan_api import wait_for_protection_pause


class PriceApplyQueueTest(unittest.TestCase):
    def test_busy_queue_retries_original_call_without_recursion(self):
        original = Mock(side_effect=[
            megaplan_transport.ProtectionPause("очередь занята", retry_after=7),
            {"data": "ok"},
        ])
        sleeps = []

        result = wait_for_protection_pause(original, sleep=sleeps.append)

        self.assertEqual({"data": "ok"}, result)
        self.assertEqual(2, original.call_count)
        self.assertEqual([7.0], sleeps)

    def test_non_retryable_pause_is_not_replayed(self):
        original = Mock(side_effect=megaplan_transport.ProtectionPause(
            "запись с неизвестным результатом", retry_after=7, retryable=False
        ))

        with self.assertRaises(megaplan_transport.ProtectionPause):
            wait_for_protection_pause(original, sleep=lambda _: self.fail("не должен ждать"))

        original.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
