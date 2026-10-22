import json
import tempfile
import unittest
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
import durable_json as storage
import installer_settlements as ledger

class LegacySafety(unittest.TestCase):
    def test_export_preserves_history_and_labels_global_scope(self):
        from openpyxl import load_workbook
        ledger.save({'operations':[],'allocations':[]})
        before=self.path.read_bytes()
        path=ledger.export_xlsx()
        book=load_workbook(path)
        text=' '.join(str(c.value or '') for row in book['Сводка'] for c in row)
        self.assertIn('без искусственного распределения',text)
        self.assertEqual(before,self.path.read_bytes())
        book.close()
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.path=Path(self.tmp.name)/'ledger.json'
        self.patch=patch.object(ledger,'LEDGER',str(self.path)); self.patch.start()
    def tearDown(self):
        self.patch.stop(); self.tmp.cleanup()
    def test_corruption_is_not_empty_history(self):
        self.path.write_text('{broken')
        with self.assertRaises(json.JSONDecodeError): ledger.load()
        self.assertEqual('{broken',self.path.read_text())
    def test_nonfinite_is_rejected_before_replacement(self):
        storage.save(str(self.path),{'value':1})
        with self.assertRaises(ValueError): storage.save(str(self.path),{'value':float('nan')})
        self.assertEqual({'value':1},storage.read(str(self.path),dict))
    def test_concurrent_accruals_preserve_all_rows(self):
        def action(index):
            return ledger.record_accrual({'report_lines':[{'source':str(index)}], 'payable_amount':index+1})
        with ThreadPoolExecutor(max_workers=8) as pool: list(pool.map(action,range(20)))
        self.assertEqual(20,len(ledger.load()['operations']))
        self.assertEqual(210,sum(x['amount'] for x in ledger.load()['operations']))
    def test_repeat_accrual_is_not_written_twice(self):
        session={'report_lines':[{'source':'fixture'}], 'payable_amount':123}
        self.assertTrue(ledger.record_accrual(session)[1])
        self.assertFalse(ledger.record_accrual(session)[1])
        self.assertEqual(1,len(ledger.load()['operations']))
    def test_invalid_accrual_has_no_record(self):
        for amount in (-1,float('inf'),float('nan')):
            with self.assertRaises(ValueError): ledger.record_accrual({'payable_amount':amount})
        self.assertFalse(self.path.exists())
    def test_repeat_with_changed_amount_cannot_hide_conflict(self):
        session={'report_lines':[{'source':'fixture'}], 'payable_amount':123}
        ledger.record_accrual(session)
        with self.assertRaisesRegex(ValueError,'другой суммой'):
            ledger.record_accrual({**session,'payable_amount':124})
        self.assertEqual(123,ledger.load()['operations'][0]['amount'])

    def test_new_accrual_consumes_advance_without_repricing_history(self):
        old={'payment_id':'paid','accrual_id':'old','amount':80}
        ledger.save({'operations':[{'id':'old','type':'accrual','amount':80},
            {'id':'paid','type':'payment','amount':200,'settlement_amount':180,'coefficient':0.9,'unallocated_advance':100}],
            'allocations':[old]})
        session={'report_lines':[{'source':'new'}],'payable_amount':150}
        op,_=ledger.record_accrual(session)
        data=ledger.load()
        self.assertEqual(old,data['allocations'][0])
        self.assertEqual(100,data['allocations'][1]['amount'])
        self.assertEqual(180,data['operations'][1]['settlement_amount'])
        self.assertEqual(0.9,data['operations'][1]['coefficient'])
        self.assertEqual(0,data['operations'][1]['unallocated_advance'])
        self.assertEqual(50,next(x for x in ledger.balances(data) if x['id']==op['id'])['balance'])
        ledger.record_accrual(session)
        self.assertEqual(2,len(ledger.load()['allocations']))

    def test_payment_rejects_missing_or_invalid_identity_and_method(self):
        base={'date':'29.09.2026','number':'1','recipient':'Example','file_hash':'fixture',
              'payment_method':'cash','amount':100,'path':''}
        for key,value in [('date','31.02.2026'),('number',''),('recipient',None),('file_hash',''),('payment_method','other')]:
            with self.assertRaises(ValueError):ledger.record_payment({**base,key:value})
        self.assertFalse(self.path.exists())

if __name__=='__main__': unittest.main()
