import unittest,tempfile,json,subprocess
from pathlib import Path
from types import SimpleNamespace
import kp_jobs
from unittest.mock import patch
class JobTests(unittest.TestCase):
 def test_bridge_retry_keeps_spec_and_delivers_both_documents(self):
  import bridge
  spec={'client':'Николай','items':[{'sku':'out','line_length_m':15}]}
  with patch.object(kp_jobs,'latest_failed',return_value={'spec':spec}), patch.object(bridge,'run_generate_kp',return_value={'ok':True,'path':'proposal.pdf','economics_xlsx_path':'economics.xlsx'}) as build, patch.object(bridge,'send_message'), patch.object(bridge,'send_document') as send:
   self.assertTrue(bridge.retry_failed_kp('token','owner','Повтори КП'))
   build.assert_called_once_with(spec,'owner')
   self.assertEqual([call.args[2] for call in send.call_args_list],['proposal.pdf','economics.xlsx'])
   self.assertFalse(bridge.retry_failed_kp('token','owner','новый счет'))
 def test_error_preserves_spec_and_retry_produces_both_files(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);spec={'client':'Николай','items':[{'sku':'out','line_length_m':15}]}
   failed=kp_jobs.run(spec,'owner',root,lambda _:SimpleNamespace(returncode=1,stdout='',stderr='traceback'))
   self.assertFalse(failed['ok']);self.assertEqual(spec,kp_jobs.latest_failed('owner',root)['spec']);self.assertIsNone(kp_jobs.latest_failed('other',root))
   pdf=root/'kp.pdf';pdf.write_bytes(b'pdf');xlsx=root/'econ.xlsx';xlsx.write_bytes(b'xlsx')
   expected={'ok':True,'path':str(pdf),'economics_xlsx_path':str(xlsx),'variants':[{'total':1}]}
   self.assertTrue(kp_jobs.run(spec,'owner',root,lambda _:SimpleNamespace(returncode=0,stdout=json.dumps(expected),stderr=''))['ok']);self.assertIsNone(kp_jobs.latest_failed('owner',root))
 def test_missing_economics_is_not_success(self):
  with tempfile.TemporaryDirectory() as tmp:
   result=kp_jobs.run({},'owner',tmp,lambda _:SimpleNamespace(returncode=0,stdout='{"ok":true,"variants":[{}]}',stderr=''));self.assertFalse(result['ok'])
 def test_timeout_keeps_original_spec(self):
  with tempfile.TemporaryDirectory() as tmp:
   def timeout(_):raise subprocess.TimeoutExpired('generator',1)
   self.assertFalse(kp_jobs.run({'client':'Николай'},'owner',tmp,timeout)['ok']);self.assertEqual('Николай',kp_jobs.latest_failed('owner',tmp)['spec']['client'])
