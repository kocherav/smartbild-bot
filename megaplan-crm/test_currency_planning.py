import unittest

from currency_planning import CurrencyPlanningError, parse_cbr_markup, plan_invoice_spec


def fixed_rate(currency, date):
    assert currency == "EUR"; assert date == "26.09.2026"
    return {"currency": "EUR", "rate": 100.0, "effective_date": "25.09.2026"}


class CurrencyPlanningTest(unittest.TestCase):
    def test_markup_parser(self):
        self.assertEqual(parse_cbr_markup("Оплата: ЦБ + 3%"), 3)
        self.assertEqual(parse_cbr_markup("Курс ЦБ РФ плюс 5 процентов"), 5)
        self.assertEqual(parse_cbr_markup(""), 0)

    def test_foreign_invoice_becomes_rub_plan_and_keeps_original_values(self):
        spec = {"invoice": {"currency": "EUR", "total": 1000, "date": "26.09.2026", "payment_note": "ЦБ + 3%"},
                "updates": [{"source_total": 800, "material_cost_used": 800, "qty_used": 1}],
                "unallocated": [{"amount": 200, "qty": 1}]}
        actual = plan_invoice_spec(spec, fixed_rate)
        doc = actual["invoice"]
        self.assertEqual(doc["foreign_total"], 1000)
        self.assertEqual(doc["cbr_rate"], 100)
        self.assertEqual(doc["plan_rate"], 103)
        self.assertEqual(doc["total"], 103000)
        self.assertEqual(actual["updates"][0]["foreign_source_total"], 800)
        self.assertEqual(actual["updates"][0]["source_total"], 82400)
        self.assertEqual(actual["unallocated"][0]["amount"], 20600)

    def test_bad_date_is_not_applied(self):
        with self.assertRaises(CurrencyPlanningError):
            plan_invoice_spec({"invoice": {"currency": "EUR", "total": 1, "date": "no"}}, fixed_rate)


if __name__ == "__main__":
    unittest.main()
