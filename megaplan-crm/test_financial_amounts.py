import unittest
from unittest.mock import patch
import financial_amounts as amounts


class FinancialAmountsTest(unittest.TestCase):
    def setUp(self):
        fixture = {'version': 1, 'overrides': {'853': {'7479': {
            'cost_material': {'basis': 'line_total', 'reason': 'isolated test fixture'}
        }}}}
        self.override = patch.object(amounts, 'load_overrides', return_value=fixture)
        self.override.start()
        self.addCleanup(self.override.stop)

    def test_unit_amount_is_multiplied_once(self):
        row={"offer_row_id":"x","qty":10,"cost_material":15}
        result=amounts.component_values("none",row,"cost_material")
        self.assertEqual("unit",result["basis"])
        self.assertEqual(150,result["line_total"])

    def test_historical_line_total_is_not_multiplied(self):
        row={"offer_row_id":"7479","qty":158,"cost_material":135000}
        result=amounts.component_values("853",row,"cost_material")
        self.assertEqual("line_total",result["basis"])
        self.assertEqual(135000,result["line_total"])
        self.assertAlmostEqual(135000/158,result["unit"])

    def test_suspicious_default_unit_is_reported_not_changed(self):
        row={"offer_row_id":"x","name":"Трасса","qty":100,"sell_price":10,"cost_material":5000}
        audit=amounts.audit_entry("none",row)
        self.assertEqual("line_total",audit[0]["suggested_basis"])


if __name__ == "__main__":
    unittest.main()
