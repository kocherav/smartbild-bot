import sqlite3
import json
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
import installer_material_delivery as delivery
import bridge


class MaterialAccessTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.accounts=Path(self.tmp.name)/'accounts.db'
        self.installations=Path(self.tmp.name)/'installations.db'
        with sqlite3.connect(self.accounts) as db:
            db.execute('CREATE TABLE accounts(chat TEXT,profile TEXT)')
            db.execute("INSERT INTO accounts VALUES('sergey','1000142')")
            db.execute("INSERT INTO accounts VALUES('other','other-profile')")
        with sqlite3.connect(self.installations) as db:
            db.execute('CREATE TABLE installations(deal_id TEXT,installer_ref TEXT,status TEXT)')
            db.execute("INSERT INTO installations VALUES('894','1000142','transferred')")

    def check(self,chat='sergey',deal='894',test=''):
        delivery.authorize(self.installations,self.accounts,chat,deal,test)

    def test_current_assignee_and_configured_test_allowed(self):
        self.check();self.check('test',test='test')

    def test_unknown_and_other_installer_denied(self):
        for chat in ['unknown','other']:
            with self.assertRaises(PermissionError):self.check(chat)

    def test_closed_or_reassigned_denied(self):
        with sqlite3.connect(self.installations) as db:db.execute("UPDATE installations SET status='closed'")
        with self.assertRaises(PermissionError):self.check()
        with sqlite3.connect(self.installations) as db:db.execute("UPDATE installations SET status='transferred',installer_ref='other-profile'")
        with self.assertRaises(PermissionError):self.check()

    def test_missing_or_invalid_deal_denied(self):
        for deal in ['999','../894','']:
            with self.assertRaises(PermissionError):self.check(deal=deal)

    def test_button_visible_and_does_not_change_dialog(self):
        self.assertIn('📦 Материалы по счетам',str(bridge.INSTALLER_INSTALLATION_KEYBOARD))
        state={'pending':'installation_object','installation_deal_id':'894'}
        with patch.object(bridge,'current_deal_ui_state',return_value=state), \
             patch.object(bridge,'send_message'),patch.object(bridge,'update_deal_ui_state') as update, \
             patch.object(bridge.subprocess,'run',return_value=type('Result',(),{'stdout':'{"ok":false,"error":"denied"}'})()), \
             patch.object(bridge,'send_document') as send:
            self.assertTrue(bridge.handle_installer_ui('token','sergey','📦 Материалы по счетам'))
        update.assert_not_called();send.assert_not_called()

    def test_button_sends_pdf_then_excel_without_resetting_state(self):
        folder=Path(self.tmp.name)/'files';folder.mkdir()
        pdf=folder/'materials.pdf';xlsx=folder/'materials.xlsx'
        pdf.write_bytes(b'pdf');xlsx.write_bytes(b'xlsx')
        result={'ok':True,'pdf':str(pdf),'xlsx':str(xlsx),'confirmed_positions':1}
        state={'pending':'installation_object','installation_deal_id':'894'}
        with patch.object(bridge,'current_deal_ui_state',return_value=state), \
             patch.object(bridge,'send_message'),patch.object(bridge,'update_deal_ui_state') as update, \
             patch.object(delivery,'authorize') as auth, \
             patch.object(bridge.subprocess,'run',return_value=type('Result',(),{'stdout':json.dumps(result)})()), \
             patch.object(bridge,'send_document',return_value=True) as send:
            bridge.handle_installer_ui('token','sergey','📦 Материалы по счетам')
        self.assertEqual([c.args[2] for c in send.call_args_list],[str(pdf),str(xlsx)])
        auth.assert_called_once();update.assert_not_called()
        self.assertFalse(folder.exists())


if __name__=='__main__':unittest.main()
