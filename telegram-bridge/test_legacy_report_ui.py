from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch,Mock
from copy import deepcopy
import legacy_report_ui as ui
import bridge

class LegacyUITests(unittest.TestCase):
    def test_existing_mapping_can_be_replaced_by_extra_without_changing_amount(self):
        session={'report_lines':[{'source':'Доставка','amount':4000,'qty':.133,'work_item_id':'215'}]}
        preview={'review':[{'source_key':'line:0'}]}
        result=ui.apply_mapping(session,preview,ui.EXTRA)
        self.assertTrue(result['report_lines'][0]['extra_cost_confirmed'])
        self.assertNotIn('work_item_id',result['report_lines'][0])
        self.assertEqual(4000,result['report_lines'][0]['amount'])
        self.assertEqual('215',session['report_lines'][0]['work_item_id'])
    def test_already_accepted_source_does_not_offer_another_confirm(self):
        app=Mock(); app.run_installation_workflow.return_value={'ok':True,'result':{
            'already_accepted':True,'receipt':{'reports':[{'deal_id':'1'}],'total':'400'}}}
        self.assertFalse(ui.stage(app,'token','manager',{}))
        self.assertIsNone(app.update_deal_ui_state.call_args.kwargs['pending'])
        self.assertIn('уже принят',app.send_message.call_args.args[2])
    def test_incomplete_history_is_not_displayed_as_confirmed_debt(self):
        text=bridge.installation_balance_text({'settlements_complete':False,'debt':999})
        self.assertIn('не подтверждена',text); self.assertNotIn('999',text)
        self.assertIn('999',bridge.installation_balance_text({'settlements_complete':True,'debt':999}))
    def test_mapping_requires_explicit_converted_quantity(self):
        session={'report_lines':[{'source':'Cable','unit':'шт','qty':1,'amount':200}]}
        preview={'review':[{'deal_id':'1','source_key':'line:0','quantity':1,'unit':'шт'}],
                 'candidates_by_deal':{'1':[{'id':5,'unit':'м','rate':100}]}}
        with self.assertRaises(ValueError):ui.apply_mapping(session,preview,'5')
        updated=ui.apply_mapping(session,preview,'5; 2')
        self.assertEqual(2,updated['report_lines'][0]['qty']); self.assertEqual(200,updated['report_lines'][0]['amount'])
        self.assertEqual('шт',session['report_lines'][0]['unit'])
        with self.assertRaises(ValueError):ui.apply_mapping(session,preview,'6; 2')

    def test_stage_only_previews_never_accepts(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'report.pdf'; source.write_bytes(b'fixture')
            app=Mock(); app.run_installation_workflow.return_value={'ok':True,'result':{'ready':True,'matched':[
                {'deal_id':'1','work_item_id':'5','name':'Work','quantity':'2','unit':'м','amount':'200'}], 'total':'200','fingerprint':'hash'}}
            self.assertTrue(ui.stage(app,'token','manager',{'source_path':str(source)}))
            self.assertEqual(['preview_legacy_report'],[c.args[0]['action'] for c in app.run_installation_workflow.call_args_list])
            self.assertEqual(ui.PENDING_CONFIRM,app.update_deal_ui_state.call_args.kwargs['pending'])

    def test_old_approve_button_prepares_new_review_without_accrual(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            with (patch.multiple(bridge,RUNTIME_ACTIVE=True,UI_CONTEXT=None,INSTALLER_CHAT_IDS=set(),
                      DEAL_UI_STATE_FILE=str(root/'state.json'),DEAL_UI_STATE_LOCK_FILE=str(root/'state.lock')),
                  patch.object(ui,'stage') as stage,patch.object(bridge,'run_installer_settlements') as accrue,
                  patch.object(bridge,'build_installer_report_result') as render):
                bridge.UI_CONTEXT=bridge.ui_state_store().bind('manager','1')
                bridge.update_deal_ui_state('manager',pending='installer_report_review',installer_report={'exceptions':[]})
                bridge.handle_deal_ui('token','manager','✅ Утвердить черновик',_background=True)
                stage.assert_called_once(); accrue.assert_not_called(); render.assert_not_called()

    def test_invalid_legacy_payable_cannot_commit_canonical_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            with (patch.multiple(bridge,RUNTIME_ACTIVE=True,UI_CONTEXT=None,INSTALLER_CHAT_IDS=set(),
                      DEAL_UI_STATE_FILE=str(root/'state.json'),DEAL_UI_STATE_LOCK_FILE=str(root/'state.lock')),
                  patch.object(bridge,'send_message'),patch.object(bridge,'run_installation_workflow') as commit,
                  patch.object(bridge,'build_installer_report_result',return_value={'ok':True,'path':'fixture'})):
                bridge.UI_CONTEXT=bridge.ui_state_store().bind('manager','1')
                bridge.update_deal_ui_state('manager',pending=ui.PENDING_CONFIRM,installer_report={'exceptions':[]})
                bridge.handle_deal_ui('token','manager',ui.CONFIRM,_background=True)
                commit.assert_not_called()

    def test_confirmed_bundle_survives_deferred_ledger_projection(self):
        for projection in ({'ok':True,'result':{}},{'ok':True,'result':{'pending_errors':{'digest':'OSError'}}}):
            with tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp)
                with (patch.multiple(bridge,RUNTIME_ACTIVE=True,UI_CONTEXT=None,INSTALLER_CHAT_IDS=set(),
                          DEAL_UI_STATE_FILE=str(root/'state.json'),DEAL_UI_STATE_LOCK_FILE=str(root/'state.lock')),
                      patch.object(bridge,'send_message'),patch.object(bridge,'send_document'),
                      patch.object(bridge,'save_approved_installer_report') as saved,
                      patch.object(bridge,'save_installer_fact_registry') as facts,
                      patch.object(bridge,'run_installer_settlements') as old_accrual,
                      patch.object(bridge,'run_installation_workflow',side_effect=[{'ok':True,'result':{}},projection]) as commit,
                      patch.object(bridge,'build_installer_report_result',return_value={'ok':True,'path':'fixture.xlsx','deal_files':[]})):
                    bridge.UI_CONTEXT=bridge.ui_state_store().bind('manager','1')
                    bridge.update_deal_ui_state('manager',pending=ui.PENDING_CONFIRM,
                        installer_report={'exceptions':[],'payable_amount':400},installer_bundle_digest='digest',installer_bundle_preview={'fingerprint':'hash'})
                    bridge.handle_deal_ui('token','manager',ui.CONFIRM,_background=True)
                    self.assertEqual(['accept_legacy_report','sync_legacy_ledger'],[c.args[0]['action'] for c in commit.call_args_list])
                    old_accrual.assert_not_called(); saved.assert_called_once(); facts.assert_called_once()
                    self.assertEqual('installer_report_upload',bridge.UI_CONTEXT.state['pending'])

    def test_render_failure_returns_to_review_without_commit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            with (patch.multiple(bridge,RUNTIME_ACTIVE=True,UI_CONTEXT=None,INSTALLER_CHAT_IDS=set(),
                      DEAL_UI_STATE_FILE=str(root/'state.json'),DEAL_UI_STATE_LOCK_FILE=str(root/'state.lock')),
                  patch.object(bridge,'send_message'),patch.object(bridge,'run_installation_workflow') as commit,
                  patch.object(bridge,'build_installer_report_result',return_value={'ok':False,'error':'fixture'})):
                bridge.UI_CONTEXT=bridge.ui_state_store().bind('manager','1')
                bridge.update_deal_ui_state('manager',pending=ui.PENDING_CONFIRM,installer_report={'exceptions':[],'payable_amount':400})
                bridge.handle_deal_ui('token','manager',ui.CONFIRM,_background=True)
                commit.assert_not_called()
                self.assertEqual('installer_report_review',bridge.UI_CONTEXT.state['pending'])

class MaterialDecisionTests(unittest.TestCase):
    def test_scoped_material_decision_and_no_source_mutation(self):
        session={'report_lines':[{'kind':'Материал','source':'Cable','deal_id':'1','amount':50}]}
        preview={'cost_review':[dict(session['report_lines'][0],source_key='line:0')],'candidates_by_deal':{'1':[]}}
        result=ui.apply_material_decision(session,preview,ui.COST_ADD)
        self.assertTrue(result['report_lines'][0]['cost_confirmed'])
        self.assertNotIn('cost_confirmed',session['report_lines'][0])
        with self.assertRaises(ValueError):ui.apply_material_decision(session,preview,'да')
        changed=ui.apply_material_decision(session,preview,'2')
        self.assertEqual('2',changed['report_lines'][0]['deal_id'])

if __name__=='__main__':unittest.main()
