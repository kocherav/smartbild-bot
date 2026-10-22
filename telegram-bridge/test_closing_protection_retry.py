import os,tempfile,unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch
import closing_runtime as c
from closing_workflow import Registry
from megaplan_transport import ProtectionPause

class ClosingProtectionRetryTest(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name);self.reg=Registry(self.root/'jobs.json')
  self.reg.change(lambda d:d['jobs'].update({'job':{'id':'job','deal_id':'858','mode':'live','status':'ready','receipts':{'done':{'ok':True}}}}))
  for p in [patch.object(c,'BASE',self.root),patch.object(c,'registry',return_value=self.reg),patch.object(c,'env',return_value={'TELEGRAM_CHAT_ID':'owner'}),patch.object(c,'recipient',return_value='tanya')]:p.start();self.addCleanup(p.stop)
 def test_foreground_reserved_budget_and_environment_restored(self):
  with patch.dict(os.environ,{'MEGAPLAN_PRIORITY':'background'}),patch.object(c,'_process',side_effect=lambda key:self.assertEqual('foreground',os.environ['MEGAPLAN_PRIORITY'])):
   c.process('job');self.assertEqual('background',os.environ['MEGAPLAN_PRIORITY'])
 def test_budget_pause_is_scheduled_and_tick_does_not_retry_early(self):
  with patch.object(c,'record_transfer',side_effect=ProtectionPause('budget',retry_after=300)) as call,patch.object(c,'tg') as tg:
   c.process('job');c.process('job');self.assertEqual(1,call.call_count);self.assertEqual(1,tg.call_count)
  job=self.reg.get('job');self.assertIn('protection_retry_at',job);self.assertEqual({'ok':True},job['receipts']['done'])
 def test_due_retry_completes_without_changing_receipts(self):
  self.reg.patch('job',protection_retry_at=(c.now()-timedelta(seconds=1)).isoformat(),protection_retries=2)
  def delivery(job):return self.reg.patch('job',status='completed',last_error=None)
  with patch.object(c,'record_transfer',side_effect=lambda j:j),patch.object(c,'publish'),patch.object(c,'delivery',side_effect=delivery):c.process('job')
  job=self.reg.get('job');self.assertEqual('completed',job['status']);self.assertEqual(0,job['protection_retries'])
 def test_exhaustion_has_working_owner_only_resume(self):
  self.reg.patch('job',protection_retries=4)
  with patch.object(c,'record_transfer',side_effect=ProtectionPause('budget')),patch.object(c,'tg') as tg:c.process('job');self.assertIn('reply_markup',tg.call_args.args[1])
  self.assertTrue(self.reg.get('job')['protection_retry_exhausted'])
  with patch.object(c,'tg'):
   for actor in ('stranger','owner'):
    c.callback({'id':'q','from':{'id':actor},'message':{'chat':{'id':actor}},'data':'closing:job:retry'})
    self.assertEqual(actor!='owner',self.reg.get('job')['protection_retry_exhausted'])
 def test_uncertain_write_is_not_a_timed_retry(self):
  with patch.object(c,'record_transfer',side_effect=ProtectionPause('unknown write',retryable=False)),patch.object(c,'tg') as tg:
   c.process('job');self.assertNotIn('reply_markup',tg.call_args.args[1])
  self.assertIsNone(self.reg.get('job')['protection_retry_at'])
if __name__=='__main__':unittest.main()
