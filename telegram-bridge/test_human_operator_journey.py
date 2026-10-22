import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import bridge
import installer_onboarding


class TelegramOperator:
    def __init__(self, steps):
        self.steps = list(steps)
        self.update_id = 0
        self.message_id = 100
        self.controls = {}
        self.messages = []
        self.transcript = []

    def api(self, _token, method, params=None, **_kwargs):
        params = params or {}
        if method == 'sendMessage':
            self.message_id += 1
            self.messages.append(params.get('text') or '')
            self.transcript.append({'actor': 'bot', 'kind': 'message', 'text': params.get('text') or ''})
            markup = json.loads(params.get('reply_markup') or '{}')
            for row in markup.get('inline_keyboard') or []:
                for button in row:
                    self.controls[button.get('text')] = button.get('callback_data')
            return {'ok': True, 'result': {'message_id': self.message_id}}
        if method == 'getUpdates':
            if not self.steps:
                raise KeyboardInterrupt()
            self.update_id += 1
            kind, value = self.steps.pop(0)
            if kind == 'text':
                self.transcript.append({'actor': 'tester', 'kind': 'message', 'text': value})
                return {'ok': True, 'result': [{'update_id': self.update_id, 'message': {
                    'message_id': self.update_id, 'date': 1, 'chat': {'id': 'owner', 'type': 'private'},
                    'from': {'id': 'owner'}, 'text': value}}]}
            callback_data = self.controls.get(value)
            if not callback_data:
                raise AssertionError('Кнопка не была показана человеку: ' + value)
            self.transcript.append({'actor': 'tester', 'kind': 'button', 'text': value})
            return {'ok': True, 'result': [{'update_id': self.update_id, 'callback_query': {
                'id': 'callback-' + str(self.update_id), 'from': {'id': 'owner'},
                'data': callback_data, 'message': {'message_id': self.message_id, 'chat': {'id': 'owner'}}}}]}
        return {'ok': True, 'result': {}}


class TelegramPollingMechanicsTests(unittest.TestCase):
    def test_status_confirmation_transport_with_explicitly_synthetic_boundary(self):
        operator = TelegramOperator([
            ('text', '🤝 Работа со сделками'),
            ('text', '🔢 Найти по номеру'),
            ('text', '990000'),
            ('text', '🔄 Изменить статус'),
            ('text', '➡️ SYNTHETIC TARGET'),
            ('click', '✅ Подтвердить'),
        ])
        deal = {'id': '990000', 'client': 'SYNTHETIC CLIENT', 'status': 'SYNTHETIC SOURCE', 'transitions': [
            {'state_id': 'TEST-STATE', 'name': 'SYNTHETIC TARGET', 'enabled': True}], 'positions_count': 1}
        moved = []

        def browser(spec, **_kwargs):
            if spec['action'] == 'get_cached':
                return {'ok': True, 'deal': dict(deal)}
            if spec['action'] == 'move_status':
                moved.append(dict(spec))
                changed = dict(deal, status='SYNTHETIC TARGET', transitions=[])
                return {'ok': True, 'deal': changed}
            raise AssertionError('Unexpected CRM action: ' + repr(spec))

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            def background(job, *_args, **_kwargs):
                job()
            with (patch.multiple(bridge, RUNTIME_ACTIVE=False, UI_CONTEXT=None, MANAGER_CHAT_ID=None,
                                 INSTALLER_NOTIFY_CHAT_ID=None, WORKFLOW_DB_FILE=str(root/'runtime.sqlite3'),
                                 DEAL_UI_STATE_FILE=str(root/'state.json'), DEAL_UI_STATE_LOCK_FILE=str(root/'state.lock'),
                                 PENDING_TRANSITIONS_FILE=str(root/'transitions.json')),
                  patch.object(bridge.invoice_tasks, 'pause'),
                  patch.object(bridge, 'load_env', return_value={'TELEGRAM_BOT_TOKEN': 'fake', 'TELEGRAM_CHAT_ID': 'owner'}),
                  patch.object(bridge, 'get_or_create_session_id', return_value='human-journey'),
                  patch.object(bridge, 'get_offset', return_value=0), patch.object(bridge, 'save_offset'),
                  patch.object(bridge, 'configure_bot_commands'), patch.object(bridge, 'recover_interrupted_document_jobs', return_value=[]),
                  patch.object(bridge, 'latest_processing_document_job', return_value=None),
                  patch.object(bridge, 'latest_retryable_document_job', return_value=None),
                  patch.object(bridge, 'run_singleton_background_job'),
                  patch.object(bridge, 'run_background_job', side_effect=background),
                  patch.object(bridge, 'run_deal_browser', side_effect=browser),
                  patch.object(installer_onboarding, 'members', return_value=set()),
                  patch.object(bridge, 'tg_api', side_effect=operator.api)):
                with self.assertRaises(KeyboardInterrupt):
                    bridge.main()

                final_state = bridge.current_deal_ui_state('owner')

        self.assertEqual([{'action': 'move_status', 'deal_id': '990000', 'state_id': 'TEST-STATE'}], moved)
        self.assertTrue(any('Статус действительно изменён' in message for message in operator.messages))
        self.assertEqual('990000', final_state.get('current_deal_id'))
        self.assertIsNone(final_state.get('pending_transition'))


if __name__ == '__main__':
    unittest.main()
