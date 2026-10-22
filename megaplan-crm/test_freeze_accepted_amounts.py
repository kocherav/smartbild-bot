import sqlite3
import unittest
from freeze_accepted_amounts import freeze


class FreezeTest(unittest.TestCase):
    def db(self):
        db=sqlite3.connect(':memory:')
        db.executescript('''CREATE TABLE reports(id INTEGER, deal_id TEXT,status TEXT);
        CREATE TABLE work_items(id INTEGER,rate REAL);
        CREATE TABLE report_items(id INTEGER,report_id INTEGER,work_item_id INTEGER,accepted_qty REAL,accepted_amount REAL);
        CREATE TABLE audit_log(id INTEGER PRIMARY KEY,deal_id TEXT,entity TEXT,entity_id TEXT,action TEXT,actor TEXT,payload TEXT,created_at TEXT);
        INSERT INTO reports VALUES(1,'example','approved'); INSERT INTO work_items VALUES(1,100);
        INSERT INTO report_items VALUES(1,1,1,2,NULL);''')
        self.addCleanup(db.close); return db

    def test_dry_run_does_not_mutate(self):
        db=self.db(); self.assertFalse(freeze(db,1)['applied'])
        self.assertIsNone(db.execute('SELECT accepted_amount FROM report_items').fetchone()[0])

    def test_expected_total_required_and_frozen_amount_survives_rate_change(self):
        db=self.db()
        with self.assertRaises(ValueError): freeze(db,1,'199')
        self.assertTrue(freeze(db,1,'200')['applied'])
        db.execute('UPDATE work_items SET rate=999'); db.commit()
        self.assertEqual(200,db.execute('SELECT accepted_amount FROM report_items').fetchone()[0])


if __name__=='__main__': unittest.main()
