from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import bridge
from workflow_runtime import Store


class InstallerDialogTest(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup); root=Path(temp.name)
        p=patch.multiple(bridge,RUNTIME_ACTIVE=True,UI_CONTEXT=None,MANAGER_CHAT_ID='manager',
            DEAL_UI_STATE_FILE=str(root/'state.json'),DEAL_UI_STATE_LOCK_FILE=str(root/'state.lock'),WORKFLOW_DB_FILE=str(root/'runtime.sqlite3'))
        p.start(); self.addCleanup(p.stop)
        bridge.UI_CONTEXT=bridge.ui_state_store().bind('installer','1')

    def test_menu_is_not_appended_to_report_text(self):
        bridge.update_deal_ui_state('installer',pending='installation_report_collect',installation_report_id=1)
        with patch.object(bridge,'run_installation_workflow') as command,patch.object(bridge,'send_message'):
            bridge.handle_installer_ui('token','installer','⬅️ Главное меню')
        command.assert_not_called(); self.assertIsNone(bridge.current_deal_ui_state('installer').get('pending'))

    def test_incoming_report_does_not_replace_managers_active_invoice(self):
        bridge.ui_state_store().update('manager',{'pending':'supplier_invoice_confirm','current_deal_id':'894'})
        bridge.update_deal_ui_state('installer',pending='installation_report_collect',installation_report_id=12)
        result={'ok':True,'result':{'report':{'id':12,'report_no':2,'deal_id':'853'},'items':[]}}
        with patch.object(bridge,'run_installation_workflow',return_value=result),patch.object(bridge,'send_message'):
            bridge.handle_installer_ui('token','installer','✅ Все материалы отправлены')
        self.assertEqual('supplier_invoice_confirm',bridge.ui_state_store().current('manager')['pending'])
        self.assertEqual('12',Store(bridge.WORKFLOW_DB_FILE).notifications('manager','installation_report')[0]['object_id'])

    def test_installer_cannot_open_manager_action_via_legacy_state(self):
        bridge.update_deal_ui_state('installer',pending='installer_report_legacy')
        with patch.object(bridge,'handle_deal_ui') as manager,patch.object(bridge,'send_message'):
            bridge.handle_installer_ui('token','installer','✅ Принять монтажный отчёт')
        manager.assert_not_called()


if __name__=='__main__': unittest.main()
