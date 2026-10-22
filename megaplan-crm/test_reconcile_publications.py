import tempfile
from pathlib import Path
from unittest.mock import Mock,patch
import json
import unittest
import reconcile_publications as reconcile
import deal_browser

class PublicationRecoveryTests(unittest.TestCase):
    def test_only_exact_file_identity_is_used(self):
        api=Mock(); api._call.return_value={'data':[{'id':'1','attaches':[{'id':'other','name':'Same.xlsx'}]}, {'id':'2','attaches':[{'id':'target'}]}]}
        self.assertEqual('2',reconcile.find_comment(api,'894','target'))
        api._call.assert_called_once_with('GET','/deal/894/comments')
    def test_absent_and_ambiguous_evidence_do_not_allow_retry(self):
        for comments in ([],[{'id':str(i),'attaches':[{'id':'target'}]} for i in (1,2)]):
            api=Mock(); api._call.return_value={'data':comments}
            with self.assertRaises(ValueError):reconcile.find_comment(api,'894','target')
    def test_recovery_only_updates_local_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'registry.json'; path.write_text(json.dumps({'894':{'pending_comment_create':True,'pending_file_id':'target'}}))
            api=Mock(); api._call.return_value={'data':[{'id':'2','attaches':[{'id':'target'}]}]}
            with patch.object(deal_browser,'ECONOMICS_ATTACHMENTS_PATH',str(path)):
                result=reconcile.economics('894',api)
            self.assertEqual('2',result['comment_id']); self.assertNotIn('pending_comment_create',json.loads(path.read_text())['894'])
            self.assertEqual(['GET'],[c.args[0] for c in api._call.call_args_list]); api.upload_file.assert_not_called()

if __name__=='__main__':unittest.main()
