import unittest
from unittest.mock import patch
import test_restore_historical_detail as fixture
import installation_scope_restore as scope

class ScopeTests(unittest.TestCase):
    def setUp(self):
        fixture.RestoreTests.setUp(self)
        self.deal={'id':'1','positions':[{'id':'101','quantity':5,'unit':{'name':'усл.'},'offer':{'name':'Aggregate','Category1000045CustomFieldSebesRabot':{'value':120}}},
            {'id':'102','quantity':10,'unit':{'name':'м'},'offer':{'name':'New work','Category1000045CustomFieldSebesRabot':{'value':20}}}]}
        self.override=patch.object(scope.financial_amounts,'load_overrides',return_value={'overrides':{}});self.override.start()
    def tearDown(self):self.override.stop();fixture.RestoreTests.tearDown(self)
    def test_full_scope_preserves_facts_rates_and_repeat(self):
        before=[tuple(r) for r in self.db.execute('SELECT * FROM report_items')]
        p=scope.plan(self.path,self.deal);scope.apply(self.path,self.deal,p['fingerprint'],'owner')
        self.assertEqual(before,[tuple(r) for r in self.db.execute('SELECT * FROM report_items')])
        self.assertEqual(100,self.db.execute('SELECT rate FROM work_items WHERE id=1').fetchone()[0])
        p=scope.plan(self.path,self.deal);scope.apply(self.path,self.deal,p['fingerprint'],'owner')
        self.assertEqual(2,self.db.execute('SELECT COUNT(*) FROM work_items').fetchone()[0])
    def test_stale_plan_and_ambiguous_names_fail_closed(self):
        p=scope.plan(self.path,self.deal)
        self.db.execute('UPDATE work_items SET active=0 WHERE id=1');self.db.commit()
        with self.assertRaises(ValueError):scope.apply(self.path,self.deal,p['fingerprint'],'owner')
        self.db.execute("INSERT INTO work_items(deal_id,source_key,name,unit,planned_qty,rate,sort_order) VALUES('1','duplicate','Aggregate','усл.',1,100,2)");self.db.commit()
        with self.assertRaises(ValueError):scope.plan(self.path,self.deal)

    def test_unmatched_requires_explicit_retention(self):
        self.deal['positions'][0]['offer']['name']='Different'
        p=scope.plan(self.path,self.deal)
        with self.assertRaises(ValueError):scope.apply(self.path,self.deal,p['fingerprint'],'owner')
        p=scope.plan(self.path,self.deal,retained_extras=[1])
        scope.apply(self.path,self.deal,p['fingerprint'],'owner',retained_extras=[1])
        self.assertEqual(3,self.db.execute('SELECT COUNT(*) FROM work_items').fetchone()[0])

    def test_resolves_reference_only_unit(self):
        self.deal['positions'][1]['unit']={'id':'4'}
        with self.assertRaises(ValueError):scope.plan(self.path,self.deal)
        p=scope.plan(self.path,self.deal,{'4':'м'})
        self.assertEqual('м',p['proposals'][1]['unit'])
