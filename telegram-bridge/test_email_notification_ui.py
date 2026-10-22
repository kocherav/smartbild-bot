import unittest
from unittest.mock import patch
import bridge

class EmailNotificationTests(unittest.TestCase):
    def test_proposal_scan_cannot_replace_newer_dialog_or_keyboard(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            with (patch.multiple(bridge,UI_CONTEXT=None,DEAL_UI_STATE_FILE=str(root/'state.json'),DEAL_UI_STATE_LOCK_FILE=str(root/'lock')),
                  patch.object(bridge,'send_message',return_value=True) as send):
                def scan(request):
                    if request['action']=='scan':
                        context=bridge.ui_state_store().bind('owner','new-message')
                        bridge.ui_state_store().update('owner',{'current_deal_id':'another'},context)
                        return {'results':[{'ok':True,'deal_id':'896'}]}
                    return {'ok':True}
                with patch.object(bridge,'run_deal_proposal',side_effect=scan):
                    bridge.check_external_proposal_transitions('token','owner')
                self.assertEqual('another',bridge.ui_state_store().current('owner')['current_deal_id'])
                self.assertNotIn('pending',bridge.ui_state_store().current('owner'))
                self.assertEqual(3,len(send.call_args.args))

    def test_stage_transition_defers_when_user_writes_during_crm_lookup(self):
        import tempfile,json
        from pathlib import Path
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);watch=root/'watch.json';watch.write_text('{}')
            with (patch.multiple(bridge,RUNTIME_ACTIVE=True,UI_CONTEXT=None,MEGAPLAN_DIR=str(root),
                    PROCUREMENT_WATCH_FILE=str(watch),DEAL_UI_STATE_FILE=str(root/'state.json'),DEAL_UI_STATE_LOCK_FILE=str(root/'state.lock')),
                  patch.object(bridge,'fetch_recent_deals',return_value=[{'deal_id':'861'}]),
                  patch.object(bridge,'run_deal_browser',return_value={'ok':True,'deals':[{'id':'861','status':'Монтаж'}]}),
                  patch.object(bridge,'prepare_installation_after_transition') as prepare):
                def concurrent(_):
                    context=bridge.ui_state_store().bind('owner','new-message')
                    bridge.ui_state_store().update('owner',{'current_deal_id':'another'},context)
                    return {'ok':False,'error_code':'installation_not_prepared'}
                with patch.object(bridge,'run_installation_workflow',side_effect=concurrent):
                    bridge.check_external_procurement_transitions('token','owner')
                prepare.assert_not_called()
                self.assertEqual('another',bridge.ui_state_store().current('owner')['current_deal_id'])
                self.assertNotIn('861',json.loads(watch.read_text()))
    def test_failed_installation_read_does_not_prepare_or_consume_transition(self):
        import tempfile,json
        from pathlib import Path
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);watch=root/'watch.json';watch.write_text('{"861":"заявка"}')
            with (patch.multiple(bridge,MEGAPLAN_DIR=str(root),PROCUREMENT_WATCH_FILE=str(watch)),
                  patch.object(bridge,'current_deal_ui_state',return_value={}),
                  patch.object(bridge,'fetch_recent_deals',return_value=[{'deal_id':'861'}]),
                  patch.object(bridge,'run_deal_browser',return_value={'ok':True,'deal':{'status':'Монтаж'}}),
                  patch.object(bridge,'run_installation_workflow',return_value={'ok':False,'error':'timeout'}),
                  patch.object(bridge,'prepare_installation_after_transition') as prepare,
                  patch.object(bridge,'ui_state_store') as state):
                bridge.check_external_procurement_transitions('token','owner')
                prepare.assert_not_called();state.assert_not_called()
                self.assertEqual('заявка',json.loads(watch.read_text())['861'])
    def test_corrupt_stage_watch_cannot_restart_procurement(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'watch.json';path.write_text('{broken')
            with patch.object(bridge,'PROCUREMENT_WATCH_FILE',str(path)),patch.object(bridge,'fetch_recent_deals') as fetch:
                with self.assertRaises(ValueError):bridge.check_external_procurement_transitions('token','owner')
                fetch.assert_not_called()
    def test_background_mail_never_overwrites_active_dialog(self):
        with (patch.object(bridge.periodic_schedule,'claim',return_value=True),
              patch.object(bridge,'run_email_payment_monitor',return_value={'ok':True,'created':[{'id':'one','amount':100}]}),
              patch.object(bridge,'update_deal_ui_state') as update,
              patch.object(bridge,'send_message') as send):
            bridge.poll_email_payments('token','owner')
            update.assert_not_called()
            self.assertEqual(3,len(send.call_args.args))
            self.assertIn('Текущий диалог не изменён',send.call_args.args[2])

    def test_hourly_gate_skips_mail_access(self):
        with patch.object(bridge.periodic_schedule,'claim',return_value=False),patch.object(bridge,'run_email_payment_monitor') as poll:
            bridge.poll_email_payments('token','owner');poll.assert_not_called()

    def test_owner_opens_exact_saved_notification_without_creating_expense(self):
        state={'current_deal_id':'another'}
        candidate={'id':'candidate-1','amount':100,'date':'29.09.2026','status':'pending','exact':True,'deal_ids':['861']}
        def update(_actor,**values):state.update(values)
        with (patch.object(bridge,'current_deal_ui_state',side_effect=lambda _:dict(state)),
              patch.object(bridge,'update_deal_ui_state',side_effect=update),patch.object(bridge,'send_message'),
              patch.object(bridge,'run_email_payment_monitor',side_effect=[{'ok':True,'candidates':[candidate],'total':1},{'ok':True,'candidate':candidate}]) as monitor,
              patch.object(bridge,'run_megaplan_finance') as finance):
            bridge.handle_bank_ui('token','owner','📩 Банковские уведомления',_background=True)
            label=next(iter(state['email_payment_choices']))
            bridge.handle_bank_ui('token','owner',label,_background=True)
            self.assertEqual('candidate-1',monitor.call_args.args[0]['id'])
            self.assertEqual('email_payment_confirm',state['pending'])
            self.assertEqual('another',state['current_deal_id'])
            finance.assert_not_called()

    def test_already_created_candidate_cannot_be_applied_again(self):
        with (patch.object(bridge,'current_deal_ui_state',return_value={'pending':'email_payment_confirm','email_payment_candidate_id':'one'}),
              patch.object(bridge,'run_email_payment_monitor',return_value={'ok':True,'candidate':{'status':'created'}}),
              patch.object(bridge,'send_message'),patch.object(bridge,'run_megaplan_finance') as finance):
            bridge.handle_bank_ui('token','owner','✅ Создать расходные операции',_background=True)
            finance.assert_not_called()

if __name__=='__main__':unittest.main()
