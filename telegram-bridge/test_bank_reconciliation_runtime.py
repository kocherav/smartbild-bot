import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "hogart-scraper/finance"))
import bank_reconciliation_queue as queue
import bank_reconciliation_runtime as runtime


class BankReconciliationRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.bank = root / "bank.json"
        self.request = root / "finance/request.json"
        self.receipt = root / "bridge/receipts.json"
        self.bank.write_text(json.dumps({"transactions": [{"id": "tx-1"}]}))

    def tearDown(self):
        self.temporary.cleanup()

    def enqueue(self):
        return queue.enqueue(self.bank, self.request, self.receipt)

    def test_request_executes_once_and_receipt_is_visible_in_status(self):
        first = self.enqueue()
        calls = []
        run = lambda command: calls.append(command) or {"ok": True, "matched": [{"transaction_id": "tx-1"}]}
        outcome = runtime.poll(run, self.request, self.receipt)
        self.assertTrue(outcome["ok"])
        self.assertIsNone(runtime.poll(run, self.request, self.receipt))
        status = self.enqueue()
        self.assertEqual(1, len(calls))
        self.assertEqual("completed", status["state"])
        self.assertEqual("tx-1", status["receipt"]["result"]["matched"][0]["transaction_id"])
        self.assertEqual(0o644, os.stat(self.request).st_mode & 0o777)
        self.assertEqual(0o644, os.stat(self.receipt).st_mode & 0o777)

    def test_permission_error_is_visible_and_request_is_not_lost(self):
        self.enqueue()
        failed = runtime.poll(lambda command: (_ for _ in ()).throw(PermissionError("lock denied")),
                              self.request, self.receipt)
        self.assertFalse(failed["ok"])
        self.assertTrue(failed["notify_owner"])
        self.assertIn("lock denied", self.enqueue()["receipt"]["error"])
        recovered = runtime.poll(lambda command: {"ok": True, "matched": []},
                                 self.request, self.receipt)
        self.assertTrue(recovered["ok"])
        self.assertEqual(2, recovered["receipt"]["attempts"])

    def test_repeated_cycle_does_not_apply_transaction_twice(self):
        self.enqueue()
        applied = set()
        def reconcile(command):
            matched = []
            if "tx-1" not in applied:
                applied.add("tx-1")
                matched.append({"transaction_id": "tx-1"})
            return {"ok": True, "matched": matched}
        runtime.poll(reconcile, self.request, self.receipt)
        self.enqueue()
        runtime.poll(reconcile, self.request, self.receipt)
        self.assertEqual({"tx-1"}, applied)


if __name__ == "__main__":
    unittest.main()
