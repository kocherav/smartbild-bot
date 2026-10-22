import unittest
import bank_matcher


class MatcherTest(unittest.TestCase):
    def index(self):
        return {"invoice_numbers": {"9511": [{"deal_id": "888", "invoice_id": "819", "invoice_number": "09511", "payer_inn": "2465", "amount": "400000"}]},
                "contract_numbers": {"1.888-1709/2026": ["888"]},
                "deal_payers": {"888": ["2465"]}, "deal_labels": {"888": "1.888-1709/2026"}}

    def test_invoice_number_with_leading_zero_and_checks(self):
        item = {"id": "x", "purpose": "Оплата по счету №09511", "direction": "income",
                "counterparty_inn": "2465", "amount": "400000"}
        match, reason = bank_matcher.match_transaction(item, self.index())
        self.assertEqual("matched", reason); self.assertEqual("888", match["deal_id"])
        self.assertTrue(match["inn_confirmed"]); self.assertTrue(match["amount_confirmed"])

    def test_contract_number(self):
        item = {"id": "x", "purpose": "Аванс по Договору №1.888-1709/2026", "direction": "income",
                "counterparty_inn": "2465", "amount": "400000"}
        match, reason = bank_matcher.match_transaction(item, self.index())
        self.assertEqual("matched", reason); self.assertIn("договор", match["basis"])

    def test_standard_contract_number_uses_deal_id_when_not_cached_by_name(self):
        index = self.index(); index["contract_numbers"] = {}
        item = {"id": "x", "purpose": "Оплата по договору №1.888-1709/2026", "direction": "income",
                "counterparty_inn": "2465", "amount": "400000"}
        match, reason = bank_matcher.match_transaction(item, index)
        self.assertEqual("matched", reason)
        self.assertEqual("888", match["deal_id"])

    def test_supplier_contract_expense_is_not_auto_assigned_to_sale(self):
        item = {"id": "x", "purpose": "Оплата по договору №1.888-1709/2026", "direction": "expense",
                "counterparty_inn": "2465", "amount": "400000"}
        match, reason = bank_matcher.match_transaction(item, self.index())
        self.assertIsNone(match)
        self.assertEqual("not_found", reason)

    def test_supplier_invoice_number_does_not_match_our_sales_invoice(self):
        item = {"id": "x", "purpose": "Оплата поставщику по счету №9511", "direction": "expense",
                "counterparty_inn": "2465", "amount": "400000"}
        match, reason = bank_matcher.match_transaction(item, self.index())
        self.assertIsNone(match); self.assertEqual("not_found", reason)

    def test_conflicting_inn_blocks_income(self):
        item = {"id": "x", "purpose": "Счет №9511", "direction": "income",
                "counterparty_inn": "9999", "amount": "400000"}
        match, reason = bank_matcher.match_transaction(item, self.index())
        self.assertIsNone(match); self.assertEqual("inn_conflict", reason)


if __name__ == "__main__": unittest.main()
