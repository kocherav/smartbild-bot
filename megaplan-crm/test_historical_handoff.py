import unittest
import test_restore_historical_detail as fixture
import historical_handoff as handoff

class HandoffTests(unittest.TestCase):
    def setUp(self):
        fixture.RestoreTests.setUp(self)
        self.db.execute("UPDATE installations SET status='historical',installer_ref='1',installer_name='Installer',address='Site',contact_name='Private',contact_phone='123'");self.db.commit()
        self.auth=dict(code='Q-MIG-HANDOFF',status='answered',answer='Разрешаю передать объекты без проекта и контактов',deal_ids=['1'])
    def tearDown(self):fixture.RestoreTests.tearDown(self)
    def test_handoff_only_once_no_financial_changes(self):
        before=[tuple(r) for r in self.db.execute('SELECT * FROM report_items')]
        handoff.apply(self.path,'1',self.auth,'owner')
        self.assertEqual(('transferred','','',0),tuple(self.db.execute('SELECT status,contact_name,contact_phone,project_required FROM installations').fetchone()))
        self.assertEqual(before,[tuple(r) for r in self.db.execute('SELECT * FROM report_items')])
        self.assertTrue(handoff.apply(self.path,'1',self.auth,'owner')['already_transferred'])
    def test_no_broad_bypass(self):
        with self.assertRaises(ValueError):handoff.apply(self.path,'2',self.auth,'owner')
        self.db.execute("UPDATE installations SET status='draft'");self.db.commit()
        with self.assertRaises(ValueError):handoff.apply(self.path,'1',self.auth,'owner')

    def test_missing_address_requires_separate_scoped_decision(self):
        self.db.execute("UPDATE installations SET address=''");self.db.commit()
        with self.assertRaises(ValueError):handoff.apply(self.path,'1',self.auth,'owner')
        self.auth['address_waiver']=dict(code='Q-MIG-ADDRESS',status='answered',answer='Да разрешаю',deal_ids=['1'])
        handoff.apply(self.path,'1',self.auth,'owner')
        self.assertEqual('Адрес уточняется',self.db.execute('SELECT address FROM installations').fetchone()[0])
