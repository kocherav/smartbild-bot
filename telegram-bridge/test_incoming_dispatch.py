import tempfile
import unittest
from pathlib import Path
from workflow_runtime import Store
from incoming_dispatch import tracked

class InboxTests(unittest.TestCase):
    def test_completed_and_interrupted_routing_have_different_recovery(self):
        with tempfile.TemporaryDirectory() as directory:
            store=Store(Path(directory)/'db.sqlite3')
            updates=[{'update_id':1,'message':{'chat':{'id':'owner'},'text':'request'}}]
            iterator=tracked(updates,store);next(iterator);iterator.close();store.recover()
            self.assertEqual('1',store.interrupted_inputs('owner')[0]['update_id'])
            self.assertEqual([],store.interrupted_inputs('other'))
            updates[0]['update_id']=2
            list(tracked(updates,store));store.recover()
            self.assertEqual(1,len(store.interrupted_inputs('owner')))
    def test_pre_upgrade_received_entries_not_mislabeled_as_failed(self):
        with tempfile.TemporaryDirectory() as directory:
            store=Store(Path(directory)/'db.sqlite3');store.receive('owner',1,{})
            store.recover();self.assertEqual([],store.interrupted_inputs('owner'))
