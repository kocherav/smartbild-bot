from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import procurement_workflow as pw
from registry_transaction import locked


class RegistryTest(unittest.TestCase):
    def test_two_consumers_cannot_spend_the_same_remaining_stock(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(pw,'REGISTRY',str(Path(folder)/'procurement.json')):
            data=pw.empty_registry(); data['unallocated_stock']=[{'id':'source','available_qty':10,'available_amount':100,'allocations':[]}]
            pw.save_registry(data)
            def consume(deal):
                try: return pw.consume_unallocated_stock('source',str(deal),7,offer_row_id=str(deal))
                except ValueError: return None
            with ThreadPoolExecutor(max_workers=2) as pool:
                results=list(pool.map(consume,[1,2]))
            self.assertEqual(1,sum(x is not None for x in results))
            saved=pw.load_json(pw.REGISTRY,{})['unallocated_stock'][0]
            self.assertEqual(3,saved['available_qty']); self.assertEqual(30,saved['available_amount'])

    def test_retry_of_fully_consumed_allocation_returns_existing_record(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(pw,'REGISTRY',str(Path(folder)/'procurement.json')):
            data=pw.empty_registry(); data['unallocated_stock']=[{'id':'source','available_qty':10,'available_amount':100,'allocations':[]}]
            pw.save_registry(data)
            one=pw.consume_unallocated_stock('source','1',10,offer_row_id='1')
            two=pw.consume_unallocated_stock('source','1',10,offer_row_id='1')
            self.assertEqual(one,two)

    def test_corrupt_registry_does_not_reset_to_empty(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'registry.json'; p.write_text('{bad')
            with self.assertRaises(json.JSONDecodeError): pw.load_json(p,{})

    def test_nested_transaction_is_reentrant(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'registry.json'
            with locked(p):
                with locked(p): pass


if __name__=='__main__': unittest.main()
