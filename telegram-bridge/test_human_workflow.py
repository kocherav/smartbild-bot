from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import bridge


class HumanWorkflowTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);root=Path(tmp.name)
        env=patch.multiple(bridge,RUNTIME_ACTIVE=True,UI_CONTEXT=None,
            DEAL_UI_STATE_FILE=str(root/'state.json'),DEAL_UI_STATE_LOCK_FILE=str(root/'state.lock'),
            WORKFLOW_DB_FILE=str(root/'runtime.sqlite3'))
        env.start();self.addCleanup(env.stop);self.seq=0
        sender=patch.object(bridge,'send_message');self.send=sender.start();self.addCleanup(sender.stop)
    def turn(self,text,confirmed=False):
        self.seq+=1;bridge.UI_CONTEXT=bridge.ui_state_store().bind('owner',str(self.seq));bridge.UI_CONTEXT.confirmed_control=confirmed
        return bridge.handle_human_workflow('token','owner',text)

    def test_creation_request_is_saved_before_document_and_never_uses_old_price(self):
        text=('Создай по этому счёту новую сделку для JetCar. Включи только светильники. '
              'Продажную цену я пока не указал — спроси её.')
        with patch.object(bridge.invoice_tasks,'pause'):
            self.assertTrue(self.turn(text))
        state=bridge.current_deal_ui_state('owner')
        self.assertEqual(state['deal_creation_request'],text)
        self.assertEqual(state['deal_create_spec']['client_name'],'JetCar')
        self.assertNotIn('items',state['deal_create_spec'])

    def test_payer_write_only_after_preview_confirmation_and_readback(self):
        listed={'ok':True,'client_name':'JetCar','payers':[
            {'id':'1','name':'ООО Старый','inn':'1','selected':True},
            {'id':'2','name':'ООО Новый','inn':'2','selected':False}]}
        def payer(spec):
            if spec.get('action')=='list_deal_payers':
                if getattr(payer,'changed',False):
                    return {**listed,'payers':[{**x,'selected':x['id']=='2'} for x in listed['payers']]}
                return listed
            payer.changed=True;return {'ok':True,'payer_id':'2'}
        with patch.object(bridge,'run_payer_card_apply',side_effect=payer) as apply:
            self.turn('Давай поменяем плательщика в сделке №900')
            self.assertEqual(bridge.current_deal_ui_state('owner')['pending'],'human_payer_select')
            self.turn('Плательщик ID 2 — ООО Новый')
            self.assertEqual(bridge.current_deal_ui_state('owner')['pending'],'human_payer_confirm')
            self.assertEqual(apply.call_count,1)
            self.turn('✅ Сменить плательщика',confirmed=True)
        self.assertEqual(apply.call_count,3)
        self.assertIsNone(bridge.current_deal_ui_state('owner').get('pending'))

    def test_installer_and_executor_share_verified_employee_assignment(self):
        def browser(spec):
            if spec['action']=='search_employees':return {'ok':True,'employees':[{'id':'10','name':'Деревянко Сергей'}]}
            if spec['action']=='get':return {'ok':True,'deal':{'id':'861','executors':['Сивков Сергей']}}
            if spec['action']=='set_executor':return {'ok':True,'deal':{'id':'861','executors':['Деревянко Сергей']}}
            raise AssertionError(spec)
        with patch.object(bridge,'run_deal_browser',side_effect=browser) as api, \
             patch.object(bridge,'run_installation_workflow',return_value={'ok':True,'installation_exists':True}):
            self.turn('Давай заменим монтажника в сделке №861')
            self.turn('Сергей')
            self.turn('Сотрудник ID 10 — Деревянко Сергей')
            self.assertFalse(any(call.args[0]['action']=='set_executor' for call in api.call_args_list))
            self.turn('✅ Назначить исполнителя',confirmed=True)
            self.assertTrue(any(call.args[0]['action']=='set_executor' for call in api.call_args_list))

    def test_payment_is_read_only_and_reports_verified_sources(self):
        with patch.object(bridge,'run_deal_browser',return_value={'ok':True,'deal':{'id':'900','client':'JetCar'}}), \
             patch.object(bridge,'run_contract_invoice',return_value={'ok':True,'invoices':[{'sum':1000,'status':'drawn'},{'sum':500,'status':'cancelled'}]}), \
             patch.object(bridge,'run_bank_statement',return_value={'ok':True,'transactions':[
                 {'deal_id':'900','status':'assigned','direction':'income','amount':600},
                 {'deal_id':'900','status':'unassigned','direction':'income','amount':400}]}) as bank:
            self.turn('Давай проверим, сколько оплачено по сделке №900')
        self.assertEqual(bank.call_args.args[0]['action'],'list')
        message=self.send.call_args.args[2]
        self.assertIn('600,00', message)
        self.assertIn('400,00', message)
        self.assertNotIn('900,00', message)


if __name__=='__main__':unittest.main()
