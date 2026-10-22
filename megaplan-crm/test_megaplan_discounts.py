import unittest

from megaplan_api import MegaplanAPI


class MegaplanDiscountLedgerTest(unittest.TestCase):
    def test_uses_offer_row_sum_after_position_discount(self):
        deal = {
            "positions": [{
                "id": "discounted-row",
                "quantity": 2,
                "price": {"value": 1000},
                "sum": {"value": 1500},
                "discount": {"type": "percent", "value": 25},
                "offer": {"id": "offer-1", "name": "Тестовая позиция"},
            }],
        }

        entry = MegaplanAPI.ledger_from_deal(deal)[0]

        self.assertEqual(1000, entry["list_price"])
        self.assertEqual(1500, entry["net_line_total"])
        self.assertEqual(750, entry["sell_price"])
        self.assertEqual(1500, entry["qty"] * entry["sell_price"])

    def test_row_sum_is_used_for_an_undiscounted_position_too(self):
        deal = {
            "positions": [{
                "id": "plain-row",
                "quantity": 3,
                "price": {"value": 500},
                "sum": {"value": 1500},
                "offer": {"id": "offer-2", "name": "Обычная позиция"},
            }],
        }

        entry = MegaplanAPI.ledger_from_deal(deal)[0]

        self.assertEqual(500, entry["sell_price"])
        self.assertEqual(1500, entry["qty"] * entry["sell_price"])


if __name__ == "__main__":
    unittest.main()
