import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
import installer_onboarding as onboarding
from workflow_runtime import Store

class OnboardingTests(unittest.TestCase):
    def test_notifications_reach_both_without_changing_keyboard(self):
        import bridge
        with patch.object(onboarding,'members',return_value={'second'}),patch.object(bridge,'INSTALLER_NOTIFY_CHAT_ID','test'),patch.object(bridge,'send_message',return_value=True) as send:
            self.assertTrue(bridge.notify_installers('token','notice'))
            self.assertEqual({'test','second'},{call.args[1] for call in send.call_args_list})
            self.assertTrue(all(len(call.args)==3 for call in send.call_args_list))
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        p=patch.object(onboarding,'DB',str(Path(self.tmp.name)/'accounts.sqlite3'));p.start();self.addCleanup(p.stop)
        self.calls=[]
        self.api=lambda method,args:self.calls.append((method,args)) or {'ok':True}
    def test_unknown_start_waits_for_owner_without_access(self):
        update={'message':{'chat':{'id':2},'from':{'id':2,'first_name':'Example'},'text':'/start'}}
        self.assertTrue(onboarding.handle(update,'1',{'1','3'},self.api,{'keyboard':[]}))
        self.assertEqual(set(),onboarding.members())
        self.assertTrue(any('reply_markup' in args and args['chat_id']=='1' for _,args in self.calls))
        self.calls.clear();onboarding.handle(update,'1',{'1','3'},self.api,{})
        self.assertFalse(any(args.get('chat_id')=='1' for _,args in self.calls))
    def test_owner_approval_adds_account_idempotently_and_sends_guide(self):
        row=onboarding.request({'id':2,'first_name':'Example'})
        with self.assertRaises(ValueError):onboarding.decide(row['id'],'2','1',True)
        callback={'callback_query':{'id':'c','from':{'id':1},'message':{'chat':{'id':1}},'data':'join:yes:'+row['id']}}
        onboarding.handle(callback,'1',{'1','3'},self.api,{'keyboard':[]})
        self.assertEqual({'2'},onboarding.members())
        self.assertTrue(any(args.get('text')==onboarding.GUIDE for _,args in self.calls))
        _,changed=onboarding.decide(row['id'],'1','1',True);self.assertFalse(changed)
    def test_request_does_not_expire_owner_report_buttons(self):
        store=Store(str(Path(self.tmp.name)/'workflow.sqlite3'))
        token=store.keyboard('1',[[{'text':'Confirm report'}]])['inline_keyboard'][0][0]['callback_data'][3:]
        onboarding.handle({'message':{'chat':{'id':2},'from':{'id':2},'text':'/start'}},'1',{'1'},self.api,{})
        self.assertTrue(store.take_control('1',token)['ok'])
    def test_invitation_single_account_and_no_access_until_approval(self):
        payload=onboarding.invitation()
        row=onboarding.request({'id':2},payload)
        self.assertEqual(row['id'],onboarding.request({'id':2},payload)['id'])
        with self.assertRaises(ValueError):onboarding.request({'id':3},payload)
        self.assertEqual(set(),onboarding.members())
    def test_rejected_account_has_no_access(self):
        row=onboarding.request({'id':2});onboarding.decide(row['id'],'1','1',False)
        self.assertEqual(set(),onboarding.members())
    def test_group_cannot_register(self):
        self.assertFalse(onboarding.handle({'message':{'chat':{'id':-5},'from':{'id':2},'text':'/start'}},'1',{'1'},self.api,{}))
        self.assertEqual([],self.calls)
