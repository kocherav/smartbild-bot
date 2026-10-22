import unittest
from unittest.mock import patch
import bridge


class BundleEntryTests(unittest.TestCase):
    def test_gate_accepts_pdf_from_home_and_requested_excel(self):
        doc={'document':{'file_name':'report.pdf'}}
        for pending in (None,'','installer_report_file','installer_report_tables'):
            self.assertTrue(bridge.installer_media_allowed(doc,pending))
        self.assertFalse(bridge.installer_media_allowed(doc,'installation_object'))
        self.assertFalse(bridge.installer_media_allowed({'photo':[]},None))
        self.assertTrue(bridge.installer_media_allowed({'photo':[]},'installation_report_collect'))

    def test_button_is_visible_and_opens_explicit_file_state(self):
        self.assertIn('📤 Сборный отчёт',str(bridge.INSTALLER_USER_KEYBOARD))
        with patch.object(bridge,'current_deal_ui_state',return_value={}),patch.object(bridge,'update_deal_ui_state') as update,patch.object(bridge,'send_message'):
            bridge.handle_installer_ui('fake','installer','📤 Сборный отчёт')
        self.assertEqual('installer_report_file',update.call_args.kwargs['pending'])

    def test_review_routes_but_manager_actions_do_not(self):
        with patch.object(bridge,'current_deal_ui_state',return_value={'pending':'installer_report_review'}),patch.object(bridge,'handle_deal_ui',return_value=True) as route,patch.object(bridge,'send_message'):
            bridge.handle_installer_ui('fake','installer','📤 Передать руководителю')
            route.assert_called_once();route.reset_mock()
            bridge.handle_installer_ui('fake','installer','✅ Утвердить черновик')
            bridge.handle_installer_ui('fake','installer','💳 Учесть выплату')
            route.assert_not_called()

    def test_exception_input_cannot_open_manager_menu(self):
        with patch.object(bridge,'current_deal_ui_state',return_value={'pending':'installer_report_exception_deal'}),patch.object(bridge,'handle_deal_ui',return_value=True) as route,patch.object(bridge,'send_message'):
            bridge.handle_installer_ui('fake','installer','861');route.assert_called_once();route.reset_mock()
            bridge.handle_installer_ui('fake','installer','🤝 Работа со сделками');route.assert_not_called()
