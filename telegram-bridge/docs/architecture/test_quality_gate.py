import hashlib,tempfile,unittest
from pathlib import Path
from quality_gate import verify
class QualityGateTests(unittest.TestCase):
    def test_stale_source_and_new_module_fail_release(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'module.py';p.write_text('x=1')
            r={'successful':True,'tests':1,'ran_at':'fixture','source_dirs':[d],'source_hashes':{str(p):hashlib.sha256(p.read_bytes()).hexdigest()}}
            self.assertTrue(verify(r)['ok'])
            p.write_text('x=2')
            with self.assertRaises(ValueError):verify(r)
            p.write_text('x=1');(Path(d)/'new.py').write_text('x=3')
            with self.assertRaises(ValueError):verify(r)
    def test_skipped_or_swallowed_network_attempt_fails_release(self):
        for extra in ({'skipped':1},{'blocked_events':[{'event':'socket.connect'}]}):
            with self.assertRaises(ValueError):verify({'successful':True,**extra})
if __name__=='__main__':unittest.main()
