import unittest
import test_restore_historical_detail as fixture
import historical_work_link as link

class LinkTests(unittest.TestCase):
    def setUp(self):
        fixture.RestoreTests.setUp(self)
        self.target=dict(source_key='deal:101',name='Work',unit='м',planned_qty=20,rate=10)
        self.quantities={r[0]:10.0 for r in self.db.execute('SELECT id FROM report_items')}
    def tearDown(self):fixture.RestoreTests.tearDown(self)
    def test_preserves_amount_and_audits_original(self):
        before=[r[0] for r in self.db.execute('SELECT accepted_amount FROM report_items')]
        p=link.preview(self.path,'1',1,self.target,self.quantities,'approved source')
        link.apply(self.path,'1',1,self.target,self.quantities,'approved source',p['fingerprint'],'owner')
        self.assertEqual(before,[r[0] for r in self.db.execute('SELECT accepted_amount FROM report_items')])
        self.assertEqual(1,self.db.execute("SELECT COUNT(*) FROM audit_log WHERE action='historical_work_linked'").fetchone()[0])
        with self.assertRaises(ValueError):link.apply(self.path,'1',1,self.target,self.quantities,'approved source',p['fingerprint'],'owner')
    def test_missing_quantity_and_stale_plan(self):
        with self.assertRaises(ValueError):link.preview(self.path,'1',1,self.target,{},'source')
        p=link.preview(self.path,'1',1,self.target,self.quantities,'source')
        self.db.execute('UPDATE work_items SET rate=99');self.db.commit()
        with self.assertRaises(ValueError):link.apply(self.path,'1',1,self.target,self.quantities,'source',p['fingerprint'],'owner')

    def test_combined_quantity_keeps_both_accepted_amounts(self):
        self.db.execute("INSERT INTO work_items(id,deal_id,source_key,name,unit,planned_qty,rate,sort_order) VALUES(2,'1','other','Other','усл.',1,20,2)")
        self.db.execute("INSERT INTO report_items(id,report_id,work_item_id,declared_qty,accepted_qty,accepted_amount,status) VALUES(2,1,2,1,1,20,'accepted')");self.db.commit()
        link.merge_approved(self.path,'1',1,[2],85,'owner confirmed 85 m2','owner')
        self.assertEqual((85,120),tuple(self.db.execute('SELECT SUM(accepted_qty),SUM(accepted_amount) FROM report_items WHERE work_item_id=1').fetchone()))
        self.assertEqual(0,self.db.execute('SELECT active FROM work_items WHERE id=2').fetchone()[0])
        with self.assertRaises(ValueError):link.merge_approved(self.path,'1',1,[2],85,'owner confirmed','owner')
