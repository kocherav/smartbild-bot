import tempfile
from pathlib import Path
import unittest
import hashlib
from unittest.mock import patch
import installation_workflow as iw
import legacy_report_commit as commit

class LegacyCommitTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.p=patch.object(iw,'DB',str(Path(self.tmp.name)/'test.sqlite3')); self.p.start()
        db=iw.connect()
        for deal in ('1','2'):
            db.execute('INSERT INTO installations(deal_id,client,essence,created_at,updated_at) VALUES(?,?,?,?,?)',(deal,'Example','Example',iw.now(),iw.now()))
            db.execute('INSERT INTO work_items(deal_id,source_key,name,unit,planned_qty,rate,sort_order) VALUES(?,?,?,?,?,?,?)',(deal,'source','Монтаж','м',10,100,1))
        db.commit(); db.close()
        self.session={'payable_amount':400,'report_date':'29.09.2026','report_lines':[{'deal_id':d,'source':'Монтаж','unit':'м','qty':2,'amount':200} for d in ('1','2')]}
        source=Path(self.tmp.name)/'report.pdf'; source.write_bytes(b'fixture'); self.digest=hashlib.sha256(b'fixture').hexdigest()
        self.session['source_path']=str(source)
    def tearDown(self): self.p.stop(); self.tmp.cleanup()
    def preview(self):
        db=iw.connect()
        try:return commit.prepare(self.session,db)
        finally:db.close()
    def test_atomic_multi_deal_acceptance_and_repeat(self):
        key=self.preview()['fingerprint']
        result=commit.accept(self.session,self.digest,key,'manager')
        self.assertEqual('400',result['total']); self.assertEqual(2,len(result['reports']))
        Path(self.session['source_path']).unlink()
        self.assertTrue(commit.accept(self.session,self.digest,key,'manager')['duplicate'])
        self.assertEqual(200,iw.get_installation('1')['accepted_total'])
        self.assertEqual(200,iw.get_installation('2')['accepted_total'])
        self.assertFalse(iw.get_installation('1')['settlements_complete'])
        self.assertEqual('installer_global',iw.get_installation('1')['settlement_scope'])
    def test_extra_expense_no_quantity_no_commercial_work_closure(self):
        self.session['report_lines']=[{'deal_id':'1','source':'Доставка','amount':3000,'extra_cost_confirmed':True}]
        key=self.preview()['fingerprint'];result=commit.accept(self.session,self.digest,key,'manager')
        self.assertEqual(3000,result['additional_total'])
        ins=iw.get_installation('1');self.assertEqual(3000,ins['accepted_total'])
        self.assertEqual(1,len(ins['works']))
        db=iw.connect()
        row=db.execute("SELECT ri.accepted_qty,ri.accepted_amount FROM report_items ri JOIN work_items w ON w.id=ri.work_item_id WHERE w.cost_kind='extra_work'").fetchone()
        self.assertEqual((0,3000),tuple(row));db.close()
        self.assertTrue(commit.accept(self.session,self.digest,key,'manager')['duplicate'])
    def test_changed_plan_stops_before_any_report(self):
        key=self.preview()['fingerprint']; db=iw.connect(); db.execute("UPDATE work_items SET rate=200 WHERE deal_id='2'"); db.commit(); db.close()
        with self.assertRaises(ValueError):commit.accept(self.session,self.digest,key,'manager')
        self.assertEqual([],iw.get_installation('1')['reports'])

    def test_materials_separate_no_work_closure_and_repeat(self):
        self.session['report_lines']=[{'deal_id':'1','kind':'Материал','source':'Cable','amount':50,'cost_decision':'additional','cost_confirmed':True}]
        key=self.preview()['fingerprint'];result=commit.accept(self.session,self.digest,key,'manager')
        self.assertEqual(50,result['materials_total']);self.assertEqual('0',result['total'])
        ins=iw.get_installation('1');self.assertEqual(50,ins['accepted_total']);self.assertEqual(1,len(ins['works']));self.assertEqual(1,len(ins['materials']))
        self.assertTrue(commit.accept(self.session,self.digest,key,'manager')['duplicate'])

    def test_existing_invoice_decision_adds_no_cost(self):
        self.session['report_lines']=[{'deal_id':'1','kind':'Материал','source':'Cable','amount':50,'cost_decision':'already_accounted','cost_confirmed':True}]
        result=commit.accept(self.session,self.digest,self.preview()['fingerprint'],'manager')
        self.assertEqual([],result['reports']);self.assertEqual(0,result['materials_total'])

    def test_new_supplier_allocation_invalidates_cost_preview(self):
        import json
        self.session['report_lines']=[{'deal_id':'1','kind':'Материал','source':'Cable','amount':50,'cost_decision':'additional','cost_confirmed':True}]
        key=self.preview()['fingerprint']
        Path(self.tmp.name,'procurement_registry.json').write_text(json.dumps({'invoices':[{'number':'N','allocations':[{'deal_id':'1','amount':50}]}]}))
        with self.assertRaises(ValueError):commit.accept(self.session,self.digest,key,'manager')
        self.assertEqual([],iw.get_installation('1')['reports'])
    def test_second_deal_failure_rolls_back_first(self):
        key=self.preview()['fingerprint']; real=iw.enqueue_publication
        def enqueue(db,deal):
            if deal=='2':raise RuntimeError('fixture')
            return real(db,deal)
        with patch.object(iw,'enqueue_publication',side_effect=enqueue):
            with self.assertRaises(RuntimeError):commit.accept(self.session,self.digest,key,'manager')
        self.assertEqual([],iw.get_installation('1')['reports'])
        self.assertEqual([],iw.get_installation('2')['reports'])
    def test_changed_repeat_is_not_another_accrual(self):
        commit.accept(self.session,self.digest,self.preview()['fingerprint'],'manager')
        self.session['report_lines'][0]['amount']=300
        with self.assertRaises(ValueError):commit.accept(self.session,self.digest,'old','manager')
        self.assertEqual(200,iw.get_installation('1')['accepted_total'])

    def test_reuploaded_original_is_reported_before_remaining_quantity_matching(self):
        commit.accept(self.session,self.digest,self.preview()['fingerprint'],'manager')
        result=commit.preview(self.session)
        self.assertTrue(result['already_accepted'])
        self.assertEqual('400',result['receipt']['total'])

    def test_miscellaneous_only_does_not_fabricate_deal_or_work_volume(self):
        self.session['report_lines']=[]
        self.session['exceptions']=[{'type':'amount','source':'Прочие расходы','amount':400,'bucket':'Всякая всячина','resolution':'Всякая всячина'}]
        result=commit.accept(self.session,self.digest,self.preview()['fingerprint'],'manager')
        self.assertEqual([],result['reports']);self.assertEqual('0',result['total'])
        self.assertEqual(0,iw.get_installation('1')['accepted_total'])
        db=iw.connect();self.assertEqual(1,db.execute('SELECT COUNT(*) FROM legacy_ledger_jobs').fetchone()[0]);db.close()

    def test_ledger_projection_recovers_without_reaccepting_work(self):
        import installer_settlements as ledger
        commit.accept(self.session,self.digest,self.preview()['fingerprint'],'manager')
        Path(self.session['source_path']).unlink()
        with patch.object(ledger,'LEDGER',str(Path(self.tmp.name)/'ledger.json')):
            with patch.object(ledger,'record_accrual',side_effect=OSError('unavailable')):
                self.assertTrue(commit.sync_ledger(self.digest)['pending_errors'])
            self.assertEqual({},commit.sync_ledger(self.digest)['pending_errors'])
            self.assertEqual({},commit.sync_ledger(self.digest)['pending_errors'])
            self.assertEqual(1,len(ledger.load()['operations']))
            self.assertEqual(400,ledger.load()['operations'][0]['amount'])
        self.assertEqual(200,iw.get_installation('1')['accepted_total'])

    def test_ledger_saved_before_receipt_retry_is_idempotent(self):
        import installer_settlements as ledger
        import json
        commit.accept(self.session,self.digest,self.preview()['fingerprint'],'manager')
        db=iw.connect(); payload=json.loads(db.execute('SELECT payload FROM legacy_ledger_jobs').fetchone()[0]); db.close()
        with patch.object(ledger,'LEDGER',str(Path(self.tmp.name)/'ledger.json')):
            ledger.record_accrual(payload)
            commit.sync_ledger(self.digest)
            self.assertEqual(1,len(ledger.load()['operations']))

if __name__=='__main__':unittest.main()
