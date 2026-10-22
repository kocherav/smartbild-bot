import copy
import unittest
import json
import io
from unittest.mock import patch
import installer_settlements as ledger
import test_restore_historical_detail as fixture
from settlement_view import combined

class ViewTests(unittest.TestCase):
    def test_export_api_and_file_use_same_combined_snapshot(self):
        view={'operations':[{'id':'new','type':'accrual','amount':40}], 'allocations':[]}
        with patch.object(ledger,'current_view',return_value=view) as read, patch.object(ledger,'export_xlsx',return_value='report.xlsx') as export, patch('sys.stdin',io.StringIO('{"action":"export"}')), patch('sys.stdout',new_callable=io.StringIO) as output:
            ledger.main.__wrapped__()
        read.assert_called_once_with();export.assert_called_once_with(view)
        self.assertEqual(40,json.loads(output.getvalue())['balances'][0]['amount'])

    def setUp(self):
        fixture.RestoreTests.setUp(self)
        self.db.execute("UPDATE installations SET installer_ref='1000142'");self.db.commit()
        self.legacy={'operations':[{'id':'old','type':'accrual','amount':100,'source_hash':'old'}],'allocations':[]}
    def tearDown(self):fixture.RestoreTests.tearDown(self)
    def test_historical_report_not_recounted_native_added_without_writes(self):
        before=copy.deepcopy(self.legacy)
        self.db.execute("INSERT INTO reports(id,deal_id,report_no,status,report_date,imported) VALUES(2,'1',2,'approved','01.02.2026',0)")
        self.db.execute("INSERT INTO report_items(report_id,work_item_id,accepted_qty,accepted_amount,status) VALUES(2,1,1,40,'accepted')");self.db.commit()
        result=combined(self.legacy,self.path)
        self.assertEqual(140,sum(r['amount'] for r in result['operations']))
        self.assertEqual(before,self.legacy);self.assertEqual(2,self.db.execute('SELECT COUNT(*) FROM reports').fetchone()[0])
    def test_pending_collected_report_deduplicates_after_projection(self):
        payload={'report_date':'01.02.2026','payable_amount':60,'source_path':'file','exceptions':[{'deal_id':'1'}]}
        self.db.execute("INSERT INTO legacy_ledger_jobs VALUES(?,?,'pending','now',NULL)",('digest',json.dumps(payload)));self.db.commit()
        result=combined(self.legacy,self.path);self.assertEqual(160,sum(r['amount'] for r in result['operations']))
        self.legacy['operations'].append({'id':'new','type':'accrual','amount':60,'source_hash':'digest'})
        result=combined(self.legacy,self.path);self.assertEqual(2,len(result['operations']))
    def test_payment_preserves_saved_credit_and_conflicting_duplicate_blocks(self):
        self.db.execute("INSERT INTO payments(deal_id,source,amount,payment_date,external_id,created_at,request_id,settlement_amount,coefficient) VALUES('1','bank',100,'01.02.2026','p','now','p',94,.94)");self.db.commit()
        result=combined(self.legacy,self.path);self.assertEqual(94,result['operations'][-1]['settlement_amount'])
        self.legacy['operations'].append({'id':'old-payment','type':'payment','date':'01.02.2026','amount':100})
        with self.assertRaises(ValueError):combined(self.legacy,self.path)
