import json
import tempfile
import unittest
from pathlib import Path

import bank_registry_projection as projection


class BankRegistryProjectionTests(unittest.TestCase):
    def test_linked_cycle_movement_is_not_unassigned_and_repeat_is_noop(self):
        row = {"id": "ledger-1", "account": "4070", "date": "2026-11-08", "direction": "out",
               "amount_cents": 125050, "inn": "7701", "number": "42", "purpose": "Оплата счёта 7"}
        tx = {"id": "bot-1", "account": "4070", "date": "08.11.2026", "direction": "expense",
              "amount": "1250.50", "counterparty_inn": "7701", "document_number": "42",
              "purpose": "Оплата счёта 7", "status": "unassigned"}
        journal = {"operations": {"part": {"bank_operation_id": "ledger-1", "state": "linked",
                    "operation_id": "3198", "amount_cents": 125050, "deal_id": "807"}}}
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "registry.json"
            path.write_text(json.dumps({"transactions": [tx], "imports": []}))
            self.assertEqual(1, projection.project([row], journal, path)["registry_updates"])
            saved = json.loads(path.read_text())["transactions"][0]
            self.assertEqual("assigned", saved["status"])
            self.assertEqual(["3198"], saved["megaplan_operation_ids"])
            self.assertEqual("807", saved["deal_id"])
            self.assertEqual(0, projection.project([row], journal, path)["registry_updates"])

    def test_partial_posting_stays_unassigned(self):
        row = {"id": "ledger-1", "account": "a", "date": "2026-11-08", "direction": "out",
               "amount_cents": 200, "inn": "1", "number": "1", "purpose": "p"}
        tx = {"account": "a", "date": "08.11.2026", "direction": "expense", "amount": "2",
              "counterparty_inn": "1", "document_number": "1", "purpose": "p", "status": "unassigned"}
        journal = {"operations": {"part": {"bank_operation_id": "ledger-1", "state": "linked",
                    "operation_id": "1", "amount_cents": 100}}}
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "registry.json"; path.write_text(json.dumps({"transactions": [tx]}))
            projection.project([row], journal, path)
            self.assertEqual("unassigned", json.loads(path.read_text())["transactions"][0]["status"])


if __name__ == "__main__":
    unittest.main()
