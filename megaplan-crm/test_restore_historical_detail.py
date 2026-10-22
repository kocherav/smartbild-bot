import tempfile
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch
import installation_workflow as iw
import restore_historical_detail as repair


class RestoreTests(TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)/'test.sqlite3'
        with patch.object(iw,'DB',str(self.path)):self.db=iw.connect()
        self.db.execute("INSERT INTO installations(deal_id,client,essence,created_at,updated_at) VALUES('1','Example','Example','now','now')")
        self.db.execute("INSERT INTO work_items(id,deal_id,source_key,name,unit,planned_qty,rate,sort_order) VALUES(1,'1','legacy:aggregate','Aggregate','усл.',1,100,1)")
        self.db.execute("INSERT INTO reports(id,deal_id,report_no,status,report_date,imported) VALUES(1,'1',1,'approved','01.01.2026',1)")
        self.db.execute("INSERT INTO report_items(id,report_id,work_item_id,declared_qty,accepted_qty,accepted_amount,status) VALUES(1,1,1,1,1,100,'accepted')")
        self.db.commit()
        self.details=[dict(name='Pipe',unit='м',qty=2,amount=100,rate=50,planned_qty=10,source_row=1)]
    def tearDown(self):self.db.close();self.temp.cleanup()
    def test_total_repeat_and_original_audit(self):
        plan=repair.preview(self.path,1,1,self.details)
        result=repair.apply(self.path,1,1,self.details,plan['fingerprint'],'owner')
        self.assertEqual(100,result['original_item']['accepted_amount'])
        self.assertEqual(100,self.db.execute('SELECT SUM(accepted_amount) FROM report_items').fetchone()[0])
        self.assertTrue(repair.apply(self.path,1,1,self.details,plan['fingerprint'],'owner')['already_applied'])
        self.assertEqual(2,self.db.execute('SELECT COUNT(*) FROM report_items').fetchone()[0])
    def test_changed_plan_does_not_write(self):
        plan=repair.preview(self.path,1,1,self.details)
        self.db.execute('UPDATE work_items SET active=0 WHERE id=1');self.db.commit()
        with self.assertRaisesRegex(ValueError,'изменились'):repair.apply(self.path,1,1,self.details,plan['fingerprint'],'owner')
        self.assertEqual(1,self.db.execute('SELECT COUNT(*) FROM report_items').fetchone()[0])
    def test_failure_rolls_back_all_rows(self):
        plan=repair.preview(self.path,1,1,self.details)
        self.db.execute("CREATE TRIGGER fail_audit BEFORE INSERT ON audit_log BEGIN SELECT RAISE(ABORT,'fixture'); END");self.db.commit()
        with self.assertRaises(Exception):repair.apply(self.path,1,1,self.details,plan['fingerprint'],'owner')
        self.assertEqual(1,self.db.execute('SELECT COUNT(*) FROM report_items').fetchone()[0])
        self.assertEqual(100,self.db.execute('SELECT accepted_amount FROM report_items WHERE id=1').fetchone()[0])
    def test_excluded_existing_work_remains_excluded(self):
        self.db.execute("INSERT INTO work_items(deal_id,source_key,name,unit,planned_qty,rate,sort_order,active) VALUES('1','deal:2','Pipe','м',50,70,2,0)");self.db.commit()
        plan=repair.preview(self.path,1,1,self.details);repair.apply(self.path,1,1,self.details,plan['fingerprint'],'owner')
        self.assertEqual((0,50,70),tuple(self.db.execute("SELECT active,planned_qty,rate FROM work_items WHERE source_key='deal:2'").fetchone()))
