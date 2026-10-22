import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
import bridge
import runtime_guards
import installer_onboarding


class PollingIsolationTests(unittest.TestCase):
    def test_file_download_is_dispatched_without_blocking_following_menu(self):
        self.check_polling('owner')

    def test_installer_pdf_reaches_file_worker_through_actual_polling_gate(self):
        self.check_polling('installer')

    def test_approved_additional_installer_reaches_same_report_handler(self):
        self.check_polling('additional')

    def check_polling(self,role):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); original={name:getattr(bridge,name) for name in runtime_guards.WRITE_ACTIONS if hasattr(bridge,name)}
            owner={'id':'owner','type':'private'}
            updates=[{'update_id':1,'message':{'message_id':10,'chat':owner,'from':{'id':'owner'},'document':{'file_id':'fake','file_unique_id':'one','file_name':'invoice.pdf','file_size':10}}},
                     {'update_id':2,'message':{'message_id':11,'chat':owner,'from':{'id':'owner'},'text':'🤝 Работа со сделками'}},
                     {'update_id':3,'message':{'message_id':12,'chat':owner,'from':{'id':'owner'},'text':'/status'}}]
            if role!='owner':
                updates=updates[:1]
                updates[0]['message']['chat']={'id':'installer','type':'private'}
                updates[0]['message']['from']={'id':'installer'}
            count=0
            def telegram(_token,method,*args,**kwargs):
                nonlocal count
                if method=='getUpdates':
                    count+=1
                    if count>1: raise KeyboardInterrupt()
                    return {'ok':True,'result':updates}
                return {'ok':True}
            try:
                with (patch.multiple(bridge,RUNTIME_ACTIVE=False,UI_CONTEXT=None,MANAGER_CHAT_ID=None,INSTALLER_NOTIFY_CHAT_ID=None,
                      WORKFLOW_DB_FILE=str(root/'runtime.sqlite3'),DEAL_UI_STATE_FILE=str(root/'state.json'),
                      DEAL_UI_STATE_LOCK_FILE=str(root/'state.lock')),
                      patch.object(bridge,'load_env',return_value={'TELEGRAM_BOT_TOKEN':'fake','TELEGRAM_CHAT_ID':'owner','EDO_NOTIFY_TELEGRAM_CHAT_ID':'edo','INSTALLER_TELEGRAM_CHAT_ID':'test-installer' if role=='additional' else 'installer'}),
                      patch.object(installer_onboarding,'members',return_value={'installer'} if role=='additional' else set()),
                      patch.object(bridge,'get_or_create_session_id',return_value='fake-session'),
                      patch.object(bridge,'get_offset',return_value=0),patch.object(bridge,'save_offset'),
                      patch.object(bridge,'configure_bot_commands'),patch.object(bridge,'recover_interrupted_document_jobs',return_value=[]),
                      patch.object(bridge,'latest_processing_document_job',return_value=None),patch.object(bridge,'latest_retryable_document_job',return_value=None),
                      patch.object(bridge,'run_singleton_background_job'),patch.object(bridge,'run_background_job') as background,
                      patch.object(bridge,'download_telegram_document',return_value=('/tmp/report.pdf',None)),
                      patch.object(bridge,'process_installer_report') as intake,
                      patch.object(bridge,'send_message') as send,patch.object(bridge,'tg_api',side_effect=telegram)):
                    with self.assertRaises(KeyboardInterrupt): bridge.main()
                    self.assertEqual(1,background.call_count)
                    if role!='owner':
                        self.assertFalse(any('Откройте свой объект' in str(call) for call in send.call_args_list))
                        background.call_args.args[0]()
                        intake.assert_called_once_with('fake','installer','/tmp/report.pdf')
                        return
                    self.assertTrue(any('выберите действие' in str(call) for call in send.call_args_list))
                    self.assertEqual('2',bridge.ui_state_store().read_all()['owner']['_last_update_id'])
                    self.assertTrue(any('Текущий статус' in str(call) for call in send.call_args_list))
            finally:
                for name,fn in original.items(): setattr(bridge,name,fn)


if __name__=='__main__': unittest.main()
