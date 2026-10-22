import json
import os
import tempfile
import unittest
from unittest import mock

import hogart_procurement as hp


class FakeAPI:
    def __init__(self):
        self.calls = []

    def search_products(self, keyword=None):
        return [{"id": 701, "article": keyword}]

    def create_order(self, items, comment=None):
        self.calls.append((items, comment))
        return {"id": 55, "number": "ORD-55"}


class HogartProcurementTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.journal = os.path.join(self.temp.name, "journal.json")
        self.lock = self.journal + ".lock"
        self.paths = mock.patch.multiple(hp, JOURNAL_FILE=self.journal, LOCK_FILE=self.lock)
        self.paths.start()

    def tearDown(self):
        self.paths.stop()
        self.temp.cleanup()

    def test_skips_non_procurement_status(self):
        self.assertEqual(hp.ensure_order("1", "Монтаж", api=FakeAPI())["reason"], "status_not_procurement")

    @mock.patch.object(hp.deal_ledger, "load")
    def test_sends_only_hogart_and_never_duplicates(self, load):
        load.return_value = [
            {"name": "Haier", "qty": 2, "supplier": "hogart", "supplier_sku": "HSU-07"},
            {"name": "Монтаж", "qty": 2, "price_source": "user_stated"},
        ]
        api = FakeAPI()
        first = hp.ensure_order("888", "Закупка", api=api)
        second = hp.ensure_order("888", "Закупка", api=api)
        self.assertTrue(first["ok"])
        self.assertEqual(first["hogart_order_number"], "ORD-55")
        self.assertEqual(len(api.calls), 1)
        self.assertEqual(api.calls[0][0], [{"productId": "701", "amount": 2}])
        self.assertEqual(second["reason"], "already_recorded")

    @mock.patch.object(hp.deal_ledger, "load")
    def test_failure_is_journaled_and_not_retried(self, load):
        load.return_value = [{"name": "Haier", "qty": 1, "supplier": "hogart",
                              "supplier_sku": "HSU-09", "supplier_product_id": "9"}]
        api = FakeAPI()
        api.create_order = mock.Mock(side_effect=TimeoutError("timeout"))
        with self.assertRaises(TimeoutError):
            hp.ensure_order("999", "Закупка", api=api)
        result = hp.ensure_order("999", "Закупка", api=api)
        self.assertEqual(result["reason"], "already_recorded")
        self.assertEqual(api.create_order.call_count, 1)
        with open(self.journal, encoding="utf-8") as source:
            self.assertEqual(json.load(source)["999"]["state"], "needs_review")

    @mock.patch.object(hp.deal_ledger, "load")
    def test_partial_supplier_order_is_not_reported_as_success(self, load):
        load.return_value = [
            {"name": f"Haier {index}", "qty": 1, "supplier": "hogart",
             "supplier_sku": f"SKU-{index}", "supplier_product_id": str(index)}
            for index in range(1, 5)
        ]
        api = FakeAPI()
        api.create_order = mock.Mock(return_value={
            "id": 55, "number": "ORD-55", "orderItemsCount": 3,
        })
        result = hp.ensure_order("887", "Закупка", api=api)
        self.assertFalse(result["ok"])
        self.assertEqual(result["requested_items_count"], 4)
        self.assertEqual(result["accepted_items_count"], 3)
        with open(self.journal, encoding="utf-8") as source:
            self.assertEqual(json.load(source)["887"]["state"], "incomplete")

    def test_hogart_item_without_supplier_sku_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "артикул/модель Hogart"):
            hp.order_items([{
                "name": "Настенная сплит-система Haier Flexis",
                "qty": 1,
                "supplier": "hogart",
                "supplier_product_id": "123",
            }], FakeAPI())

    def test_order_subtracts_quantity_covered_by_internal_stock(self):
        items = hp.order_items([{
            "name": "Haier", "qty": 5, "consumed_qty": 2,
            "supplier": "hogart", "supplier_sku": "HSU-07", "supplier_product_id": "701",
        }], FakeAPI())
        self.assertEqual(3, items[0]["amount"])


if __name__ == "__main__":
    unittest.main()
