import sqlite3
import tempfile
import unittest
from pathlib import Path
from migration_transition_guard import blocked

class GuardTests(unittest.TestCase):
    def test_lifecycle_scoped_and_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'db.sqlite3'
            self.assertFalse(blocked(p,'1'))
            with sqlite3.connect(p) as db:
                db.execute('CREATE TABLE audit_log(id INTEGER PRIMARY KEY,deal_id TEXT,action TEXT)')
                db.execute("INSERT INTO audit_log VALUES(1,'1','historical_stage_migration_started')");db.commit()
                self.assertTrue(blocked(p,'1'));self.assertFalse(blocked(p,'2'))
                db.execute("INSERT INTO audit_log VALUES(2,'1','historical_stage_migration_finished')");db.commit()
                self.assertFalse(blocked(p,'1'))
