import unittest
from unittest import mock
import json
import os
import tempfile
import bridge


class ProtocolTest(unittest.TestCase):
    def test_any_deal_button_preempts_stale_developer_task_input(self):
        for deal_id in ('901','900','899','896'):
            state={'pending':'developer_task_input','current_deal_id':'old'}
            with mock.patch.object(bridge,'current_deal_ui_state',return_value=state), \
                 mock.patch.object(bridge,'select_deal') as select, \
                 mock.patch.object(bridge,'process_developer_task') as developer:
                self.assertTrue(bridge.handle_deal_ui('token','chat',f'№{deal_id} · Любая подпись',_background=True))
            select.assert_called_once_with('token','chat',deal_id)
            developer.assert_not_called()

    def test_deal_button_is_global_navigation_before_every_pending_handler(self):
        with mock.patch.object(bridge,'handle_deal_ui',return_value=True) as deal:
            self.assertTrue(bridge.handle_global_navigation('token','chat','№812 · Подпись сделки'))
        deal.assert_called_once_with('token','chat','№812 · Подпись сделки')

    def test_open_card_phrase_uses_current_deal_without_model(self):
        with mock.patch.object(bridge,'current_deal_ui_state',return_value={'current_deal_id':'901'}), \
             mock.patch.object(bridge,'select_deal') as select, \
             mock.patch.object(bridge,'ask_claude') as model:
            self.assertTrue(bridge.handle_deal_ui('token','chat','Перейти в карточку сделки',_background=True))
        select.assert_called_once_with('token','chat','901');model.assert_not_called()

    def test_deal_button_failure_stays_in_deal_route(self):
        with mock.patch.object(bridge,'run_deal_browser',return_value={'ok':False,'error':'таймаут'}), \
             mock.patch.object(bridge,'send_message') as send, \
             mock.patch.object(bridge,'process_developer_task') as developer:
            self.assertTrue(bridge.handle_deal_ui('token','chat','№777 · Сделка',_background=True))
        self.assertIn('Не удалось открыть сделку',send.call_args.args[2]);developer.assert_not_called()

    def test_recent_count_buttons_are_visible_on_narrow_screen(self):
        self.assertEqual(
            [button['text'] for button in bridge.DEAL_RECENT_KEYBOARD['keyboard'][0]],
            ['🕘 5', '🕘 10', '🕘 15'],
        )

    def test_deal_list_shows_full_essence_and_buttons_show_short_essence(self):
        long_essence = '<p>Поставка фасадных вентиляционных решёток и монтаж на объекте</p>'
        deal = {'id':'901','client':'Автосалон JetCar','description':long_essence,
                'status':'Заявка','address':''}
        with mock.patch.object(bridge,'run_deal_browser',return_value={'ok':True,'deals':[deal]}), \
             mock.patch.object(bridge,'send_message') as send:
            bridge.send_deal_list('token','chat',{'action':'list','limit':5})
        text, keyboard = send.call_args.args[2], send.call_args.args[3]
        self.assertIn('Суть: Поставка фасадных вентиляционных решёток и монтаж на объекте',text)
        label=keyboard['keyboard'][0][0]['text']
        self.assertTrue(label.startswith('№901 · Поставка фасадных'))
        self.assertLessEqual(len(label),len('№901 · ')+38)
        self.assertNotIn('<p>',label)

    def test_deal_essence_falls_back_to_address_then_client(self):
        self.assertEqual(bridge.deal_essence({'address':'Подвойского 5/19','client':'JetCar'}),'Подвойского 5/19')
        self.assertEqual(bridge.deal_essence({'client':'JetCar'}),'JetCar')

    def test_deal_essence_excludes_service_terms_after_first_sentence(self):
        description = ('Поставка светильников. Продавец: ООО «КЛИВЭЛ». '
                       'Договор и счёт на 100% предоплату. Цена включает НДС 5%.')
        self.assertEqual(bridge.deal_essence({'description':description}),'Поставка светильников')

    def test_deal_essence_has_hard_display_limit(self):
        essence=bridge.deal_essence({'description':'Очень длинный предмет сделки без точки ' * 10})
        self.assertLessEqual(len(essence),90);self.assertTrue(essence.endswith('…'))

    def test_current_stage_and_execute_read_do_not_route_to_execution_report(self):
        text = (
            'Перечитай сделку №900 непосредственно из Мегаплана, ничего не меняя. '
            'Назови клиента, номер сделки, текущий этап, общую сумму и количество позиций. '
            'Отдельно скажи, удалось ли выполнить свежее чтение из CRM или ты используешь ранее сохранённые данные.'
        )
        with mock.patch.object(bridge, 'current_deal_ui_state', return_value={}), \
             mock.patch.object(bridge, 'run_deal_browser') as browser, \
             mock.patch.object(bridge, 'send_message') as send:
            self.assertFalse(bridge.handle_current_execution_ui('token', 'chat', text))
        browser.assert_not_called()
        send.assert_not_called()

    def test_explicit_current_execution_request_still_routes(self):
        deal = {'id': '900', 'client': 'Клиент', 'name': 'Работы'}
        with mock.patch.object(bridge, 'current_deal_ui_state', return_value={}), \
             mock.patch.object(bridge, 'approved_deal_ids', return_value={'900'}), \
             mock.patch.object(bridge, 'run_deal_browser', return_value={'ok': True, 'deal': deal}), \
             mock.patch.object(bridge, 'archive_deal_labels', return_value={}), \
             mock.patch.object(bridge, 'send_current_execution') as send:
            self.assertTrue(bridge.handle_current_execution_ui(
                'token', 'chat', 'Пришли текущее выполнение по сделке 900'))
        send.assert_called_once()

    def test_real_reproduction_phrase_reads_numbered_deal_live_without_model(self):
        text = (
            'Перечитай сделку №900 непосредственно из Мегаплана, ничего не меняя. '
            'Назови клиента, номер сделки, текущий этап, общую сумму и количество позиций. '
            'Отдельно скажи, удалось ли выполнить свежее чтение из CRM или ты используешь ранее сохранённые данные.'
        )
        deal = {'id': '900', 'client': 'ООО МК', 'status': 'Подписание договора',
                'price': 758160, 'positions_count': 1}
        with mock.patch.object(bridge, 'run_deal_browser', return_value={'ok': True, 'deal': deal}) as browser, \
             mock.patch.object(bridge, 'update_deal_ui_state'), \
             mock.patch.object(bridge, 'send_message') as send:
            self.assertTrue(bridge.handle_explicit_deal_read('token', 'chat', text))
        browser.assert_called_once_with({'action': 'get', 'deal_id': '900'})
        self.assertIn('Источник: свежее чтение из Мегаплана', send.call_args.args[2])
        self.assertIn('Статус: Подписание договора', send.call_args.args[2])

    def test_failed_live_deal_read_does_not_present_cache_as_current(self):
        with mock.patch.object(bridge, 'run_deal_browser', return_value={'ok': False, 'error': 'таймаут'}), \
             mock.patch.object(bridge, 'send_message') as send:
            self.assertTrue(bridge.handle_explicit_deal_read(
                'token', 'chat', 'Покажи сделку №900, ничего не меняй'))
        self.assertIn('Ранее сохранённые данные не показываю как актуальные', send.call_args.args[2])

    def test_compound_live_deal_read_answers_every_economics_part(self):
        text = (
            'Проверь сделку №900 непосредственно в Мегаплане и ничего не изменяй. '
            'Сначала назови клиента, текущий этап и количество позиций. Затем проверь, совпадает ли '
            'общая сумма сделки с количеством, умноженным на цену позиции. Отдельно покажи общую '
            'себестоимость и разницу между продажей и себестоимостью.'
        )
        deal = {'id': '900', 'client': 'Автосалон JetCar', 'status': 'Подписание договора',
                'price': 758160, 'positions_count': 1}
        ledger = [{'name': 'LOCUS', 'qty': 18, 'sell_price': 42120,
                   'cost_material': 39780, 'cost_work': None}]
        with mock.patch.object(bridge, 'run_deal_browser', return_value={'ok': True, 'deal': deal}), \
             mock.patch.object(bridge, 'fetch_deal_ledger', return_value=ledger) as fetch, \
             mock.patch.object(bridge, 'update_deal_ui_state'), \
             mock.patch.object(bridge, 'send_message') as send:
            self.assertTrue(bridge.handle_explicit_deal_read('token', 'chat', text))
        fetch.assert_called_once_with('900', force=True)
        answer = send.call_args.args[2]
        self.assertIn('Совпадает: да', answer)
        self.assertIn('Общая себестоимость позиций: 716 040,00 ₽', answer)
        self.assertIn('Разница продажи и себестоимости: 42 120,00 ₽', answer)

    def test_compound_read_reports_unverified_when_live_ledger_is_unavailable(self):
        deal = {'id': '900', 'client': 'JetCar', 'status': 'Подписание договора',
                'price': 758160, 'positions_count': 1}
        with mock.patch.object(bridge, 'run_deal_browser', return_value={'ok': True, 'deal': deal}), \
             mock.patch.object(bridge, 'fetch_deal_ledger', return_value=None), \
             mock.patch.object(bridge, 'update_deal_ui_state'), \
             mock.patch.object(bridge, 'send_message') as send:
            bridge.handle_explicit_deal_read(
                'token', 'chat', 'Проверь сделку №900: совпадает ли сумма и какова себестоимость?')
        self.assertIn('НЕ ПРОВЕРЕНО', send.call_args.args[2])

    def test_real_comparison_phrase_reads_both_deals_without_model(self):
        text = (
            'Сравни сделки №900 и №861 непосредственно по свежим данным Мегаплана. Ничего не изменяй. '
            'Для каждой сделки назови клиента, текущий этап, общую сумму и количество позиций. '
            'Затем скажи, у какой сделки сумма больше и на сколько.'
        )
        deals = {
            '900': {'id': '900', 'client': 'JetCar', 'status': 'Подписание договора',
                    'price': 758160, 'positions_count': 1},
            '861': {'id': '861', 'client': 'Cliwell', 'status': 'Монтаж',
                    'price': 7650000, 'positions_count': 94},
        }
        with mock.patch.object(bridge, 'run_deal_browser', side_effect=lambda spec: {
                'ok': True, 'deal': deals[spec['deal_id']]} ) as browser, \
             mock.patch.object(bridge, 'update_deal_ui_state'), \
             mock.patch.object(bridge, 'send_message') as send:
            self.assertTrue(bridge.handle_explicit_deal_comparison('token', 'chat', text))
        self.assertEqual(
            [mock.call({'action': 'get', 'deal_id': '900'}), mock.call({'action': 'get', 'deal_id': '861'})],
            browser.call_args_list,
        )
        answer = send.call_args.args[2]
        self.assertIn('Сделка №900', answer)
        self.assertIn('Сделка №861', answer)
        self.assertIn('Сумма сделки №861 больше на 6 891 840,00 ₽', answer)

    def test_comparison_does_not_guess_when_one_live_read_fails(self):
        responses = [
            {'ok': True, 'deal': {'id': '900', 'price': 758160}},
            {'ok': False, 'error': 'таймаут'},
        ]
        with mock.patch.object(bridge, 'run_deal_browser', side_effect=responses), \
             mock.patch.object(bridge, 'send_message') as send:
            self.assertTrue(bridge.handle_explicit_deal_comparison(
                'token', 'chat', 'Сравни сделки №900 и №861'))
        self.assertIn('НЕ ПРОВЕРЕНО', send.call_args.args[2])
        self.assertIn('сделка №861: таймаут', send.call_args.args[2])

    def test_comparison_followup_uses_saved_pair_and_rereads_smaller_deal(self):
        text = (
            'Из этих двух сделок открой ту, у которой сумма меньше. Ещё раз свежо прочитай её '
            'из Мегаплана и назови номер, клиента, текущий этап и сумму. Ничего не изменяй.'
        )
        state = {'comparison_deals': [
            {'deal_id': '900', 'price': 758160}, {'deal_id': '861', 'price': 7650000},
        ]}
        deal = {'id': '900', 'client': 'JetCar', 'status': 'Подписание договора',
                'price': 758160, 'positions_count': 1}
        with mock.patch.object(bridge, 'current_deal_ui_state', return_value=state), \
             mock.patch.object(bridge, 'run_deal_browser', return_value={'ok': True, 'deal': deal}) as browser, \
             mock.patch.object(bridge, 'update_deal_ui_state'), \
             mock.patch.object(bridge, 'send_message') as send:
            self.assertTrue(bridge.handle_deal_comparison_followup('token', 'chat', text))
        browser.assert_called_once_with({'action': 'get', 'deal_id': '900'})
        self.assertIn('Клиент: JetCar', send.call_args.args[2])
        self.assertIn('Статус: Подписание договора', send.call_args.args[2])
        self.assertIn('повторное свежее чтение', send.call_args.args[2])

    def test_comparison_followup_without_saved_pair_does_not_guess(self):
        with mock.patch.object(bridge, 'current_deal_ui_state', return_value={}), \
             mock.patch.object(bridge, 'run_deal_browser') as browser, \
             mock.patch.object(bridge, 'send_message') as send:
            self.assertTrue(bridge.handle_deal_comparison_followup(
                'token', 'chat', 'Из этих двух сделок открой ту, у которой сумма меньше'))
        browser.assert_not_called()
        self.assertIn('НЕ ПРОВЕРЕНО', send.call_args.args[2])

    def test_create_accepts_fenced_json_but_rejects_non_object(self):
        _, spec = bridge.extract_create_megaplan_deal('CREATE_MEGAPLAN_DEAL_BEGIN\n```json\n{"client_name":"JetCar"}\n```\nCREATE_MEGAPLAN_DEAL_END')
        self.assertEqual(spec['client_name'], 'JetCar')
        _, spec = bridge.extract_create_megaplan_deal('CREATE_MEGAPLAN_DEAL_BEGIN [] CREATE_MEGAPLAN_DEAL_END')
        self.assertTrue(spec['__invalid__'])

    def test_creation_searches_and_requires_client_selection_without_model(self):
        state = {'pending': 'deal_create_client', 'deal_create_spec': {'description': 'Освещение'}}
        with mock.patch.object(bridge, 'current_deal_ui_state', return_value=state), \
             mock.patch.object(bridge, 'update_deal_ui_state') as save, \
             mock.patch.object(bridge, 'search_creation_clients', return_value={'ok': True, 'clients': [{'id':'42','name':'JetCar','kind':'company'}]}), \
             mock.patch.object(bridge, 'send_message') as send:
            self.assertTrue(bridge.handle_deal_ui('token', 'chat', 'JetCar', _background=True))
            self.assertEqual(save.call_args.kwargs['pending'], 'deal_create_client_select')
            self.assertEqual(save.call_args.kwargs['deal_create_spec'], {'description': 'Освещение', 'client_name': 'JetCar'})
            self.assertIn('карточку', send.call_args.args[2])

    def test_legacy_build_kp_is_extracted_and_hidden(self):
        reply = ('КП пересобрано.\n\nBUILD_KP: '
                 '{"client":"Татьяна","variants":[{"title":"Вариант 1",'
                 '"items":[{"source":"hogart","sku":"ABC/1","qty":1}]}]}')
        clean, spec = bridge.extract_build_kp(reply)
        self.assertEqual("КП пересобрано.", clean)
        self.assertEqual("Татьяна", spec["client"])
        self.assertNotIn("BUILD_KP", clean)
        self.assertNotIn("sku", clean)

    def test_malformed_service_payload_is_never_shown(self):
        clean, spec = bridge.extract_build_kp('Готово.\nBUILD_KP: {broken json')
        self.assertEqual("Готово.", clean)
        self.assertTrue(spec["__invalid__"])

    def test_output_firewall_removes_unconsumed_marker_and_payload(self):
        clean = bridge.sanitize_service_protocol('Нормальный ответ.\nBUILD_KP: {"secret": 1}')
        self.assertEqual("Нормальный ответ.", clean)
    def test_unimplemented_payment_protocol_is_hidden_and_not_claimed_executed(self):
        text=bridge.sanitize_service_protocol('Готово\nREGISTER_CONTRACTOR_PAYMENT_BEGIN\n```json\n{"amount":92600}\n```\nREGISTER_CONTRACTOR_PAYMENT_END')
        self.assertNotIn('REGISTER_',text);self.assertNotIn('92600',text)
        self.assertIn('не выполнено',text);self.assertNotIn('Готово',text)
    def test_installer_payment_request_routes_without_model_command(self):
        self.assertTrue(bridge.installer_payment_intent('Нужно учесть платеж в пользу монтажника и пересчитать взаиморасчёты с ним'))
        self.assertFalse(bridge.installer_payment_intent('Учти платеж поставщику'))

    def test_output_firewall_removes_unsupported_deal_update_protocol(self):
        clean = bridge.sanitize_service_protocol(
            'Понял.\nUPDATE_MEGAPLAN_DEAL\n```json\n{"deal_id":895}\n```'
        )
        self.assertEqual("Понял.", clean)

    def test_sync_deal_kp_is_extracted_and_hidden(self):
        reply = ('Обновляю сделку.\nSYNC_DEAL_KP_BEGIN\n'
                 '{"deal_id":"887","kp":{"client":"JetCar","variants":[]}}\n'
                 'SYNC_DEAL_KP_END')
        clean, spec = bridge.extract_sync_deal_kp(reply)
        self.assertEqual("Обновляю сделку.", clean)
        self.assertEqual("887", spec["deal_id"])
        self.assertNotIn("SYNC_DEAL_KP", clean)

    def test_sync_deal_kp_protocol_is_never_shown(self):
        clean = bridge.sanitize_service_protocol(
            'Обновляю.\nSYNC_DEAL_KP_BEGIN\n{"deal_id":"887"}'
        )
        self.assertEqual("Обновляю.", clean)

    def test_kp_revision_does_not_create_duplicate_deal(self):
        self.assertFalse(bridge.should_auto_create_kp_deal("Пересобери это КП, добавь работы"))
        self.assertTrue(bridge.should_auto_create_kp_deal("Пересобери КП и создай новую сделку"))

    def test_proposal_request_never_implies_new_deal(self):
        self.assertFalse(bridge.should_auto_create_kp_deal('Сделай КП по сделке 896'))
        self.assertFalse(bridge.should_auto_create_kp_deal('Собери КП для клиента'))

    def test_proposal_button_uses_selected_deal_without_llm(self):
        with mock.patch.object(bridge, 'current_deal_ui_state', return_value={'current_deal_id': '896'}), \
             mock.patch.object(bridge, 'update_deal_ui_state') as state, \
             mock.patch.object(bridge, 'send_message'), \
             mock.patch.object(bridge, 'send_deal_proposal') as generate:
            self.assertTrue(bridge.handle_deal_ui('token', 'chat', '📄 КП по сделке', _background=True))
        generate.assert_not_called()
        self.assertEqual(state.call_args.kwargs['proposal_deal_id'], '896')

    def test_proposal_explicit_id_overrides_previous_deal(self):
        with mock.patch.object(bridge, 'current_deal_ui_state', return_value={'current_deal_id': '861'}), \
             mock.patch.object(bridge, 'update_deal_ui_state') as state, \
             mock.patch.object(bridge, 'send_message'), \
             mock.patch.object(bridge, 'send_deal_proposal') as generate:
            self.assertTrue(bridge.handle_deal_ui('token', 'chat', 'Сделай КП по сделке №896', _background=True))
        generate.assert_not_called()
        self.assertEqual(state.call_args.kwargs['proposal_deal_id'], '896')

    def test_recipient_answer_uses_bound_deal_not_current_selection(self):
        with mock.patch.object(bridge, 'current_deal_ui_state', return_value={
                'current_deal_id': '861', 'pending': 'proposal_recipient', 'proposal_deal_id': '896'}), \
             mock.patch.object(bridge, 'update_deal_ui_state'), mock.patch.object(bridge, 'send_message'), \
             mock.patch.object(bridge, 'send_deal_proposal') as generate:
            self.assertTrue(bridge.handle_deal_ui('token', 'chat', 'Уважаемая Татьяна,', _background=True))
        generate.assert_called_once_with('token', 'chat', '896', recipient='Уважаемая Татьяна,')

    def test_auto_recipient_prompt_does_not_overwrite_busy_flow(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d, \
             mock.patch.object(bridge, 'DEAL_UI_STATE_LOCK_FILE', d + '/lock'), \
             mock.patch.object(bridge, 'DEAL_UI_STATE_FILE', d + '/state.json'):
            bridge.ui_state_store().save({'chat': {'pending': 'supplier_invoice_confirm'}})
            self.assertFalse(bridge.try_begin_proposal_recipient('chat', '896'))

    def test_auto_recipient_prompt_preserves_selected_deal(self):
        import tempfile
        import json
        with tempfile.TemporaryDirectory() as d, \
             mock.patch.object(bridge, 'DEAL_UI_STATE_LOCK_FILE', d + '/lock'), \
             mock.patch.object(bridge, 'DEAL_UI_STATE_FILE', d + '/state.json'), \
             mock.patch.object(bridge, 'UI_CONTEXT', None):
            bridge.ui_state_store().save({'chat': {'current_deal_id': '861'}})
            self.assertTrue(bridge.try_begin_proposal_recipient('chat', '896'))
            with open(d + '/state.json') as f: state = json.load(f)['chat']
            self.assertEqual(state['current_deal_id'], '861')
            self.assertEqual(state['proposal_deal_id'], '896')

    def test_tax_answer_is_strict_and_deterministic(self):
        self.assertEqual("none", bridge.tax_mode_from_text("БЕЗ НДС"))
        self.assertEqual("22", bridge.tax_mode_from_text("НДС 22%"))
        self.assertEqual("5", bridge.tax_mode_from_text("5%"))
        self.assertIsNone(bridge.tax_mode_from_text("сделай как в прошлый раз"))

    def test_new_hogart_price_query_requires_fresh_search(self):
        self.assertTrue(bridge.needs_fresh_hogart_search(
            "Дай цену на кондиционер Haier 2 кВт с наценкой 15%"
        ))
        self.assertTrue(bridge.needs_fresh_hogart_search("Есть ли Casarte в наличии?"))
        self.assertFalse(bridge.needs_fresh_hogart_search("Расскажи историю компании Haier"))
        self.assertFalse(bridge.needs_fresh_hogart_search("Дай цену на Daikin"))

    def test_create_deal_payload_aliases_are_normalized(self):
        spec, error = bridge.normalize_create_deal_spec({
            "client": "Зоовет", "name": "Поставка и монтаж", "tax_mode": "Без НДС",
            "items": [
                {"name": "Кондиционер", "quantity": 1, "sale_price": 17796.48},
                {"name": "Монтаж", "quantity": 1, "sale_price": 20000, "cost_work": 15000},
            ],
        })
        self.assertIsNone(error)
        self.assertEqual(spec["client_name"], "Зоовет")
        self.assertEqual(spec["tax_mode"], "none")
        self.assertEqual(spec["description"], "Поставка и монтаж")
        self.assertEqual(spec["items"][0]["qty"], 1.0)
        self.assertEqual(spec["items"][0]["unit_price"], 17796.48)

    def test_create_deal_payload_is_validated_before_subprocess(self):
        with mock.patch.object(bridge.subprocess, "run") as run:
            result = bridge.run_create_megaplan_deal({"tax_mode": "none", "items": []})
        self.assertFalse(result["ok"])
        self.assertIn("не указан клиент", result["error"])
        run.assert_not_called()

    def test_empty_deal_items_are_a_validation_error(self):
        spec, error = bridge.normalize_create_deal_spec({
            "client_name": "Светлана Дикушина", "tax_mode": "none", "items": [],
        })
        self.assertIsNone(spec)
        self.assertEqual("не указаны позиции сделки", error)

    def test_create_deal_preserves_multiline_api_error(self):
        import json
        from types import SimpleNamespace
        result = SimpleNamespace(returncode=1, stderr='', stdout=json.dumps({
            'ok': False, 'status': 422,
            'body': {'meta': {'errors': [{'message': 'Invalid unit'}]}}
        }, indent=2))
        with mock.patch.object(bridge, 'price_install_addons', return_value=([], {}, [])), \
             mock.patch.object(bridge.subprocess, 'run', return_value=result):
            r = bridge.run_create_megaplan_deal({'client_name': 'Test', 'tax_mode': 'none',
                'items': [{'name': 'Test', 'qty': 1, 'unit_price': 10}]})
        self.assertFalse(r['ok'])
        self.assertEqual(r['error'], 'Invalid unit')

    def test_numeric_tax_shortcut_is_supported(self):
        self.assertEqual(bridge.tax_mode_from_text("1"), "none")

    def test_numbered_tax_option_is_supported_without_second_prompt(self):
        self.assertEqual(bridge.tax_mode_from_text("1. Без НДС"), "none")
        self.assertEqual(bridge.tax_mode_from_text("2. НДС 22% включён в сумму 100 ₽"), "22")
        self.assertEqual(bridge.tax_mode_from_text("3) НДС 5% начисляется сверху"), "5")

    def test_contract_request_is_not_new_deal_request(self):
        self.assertTrue(bridge.is_explicit_contract_request("Создай договор по сделке 892"))
        self.assertFalse(bridge.is_explicit_new_deal_request("Создай договор по сделке 892"))
        self.assertTrue(bridge.is_explicit_new_deal_request("Создай новую сделку"))

    def test_contract_button_without_selected_deal_is_blocked_locally(self):
        with mock.patch.object(bridge, "current_deal_ui_state", return_value={}), \
             mock.patch.object(bridge, "send_message", return_value=True) as send, \
             mock.patch.object(bridge, "run_contract_builder") as builder:
            handled = bridge.handle_deal_ui("token", "chat", "📝 Подготовить договор", _background=True)
        self.assertTrue(handled)
        self.assertIn("Сначала выберите существующую сделку", send.call_args.args[2])
        builder.assert_not_called()

    def test_contract_preview_collects_date_before_signatory(self):
        preview = {"missing": ["дата договора", "адрес объекта", "ФИО подписанта"]}
        with mock.patch.object(bridge, "current_deal_ui_state", return_value={}), \
             mock.patch.object(bridge, "run_contract_builder", return_value={"ok": True, "preview": preview}), \
             mock.patch.object(bridge, "update_deal_ui_state") as update, \
             mock.patch.object(bridge, "send_message"):
            bridge.prepare_contract_preview("token", "chat", "892")
        update.assert_called_once_with("chat", pending="contract_date", contract_deal_id="892")

    def test_contract_preview_exposes_signatory_and_correction_actions(self):
        preview = {
            "number": "892-Д", "date": "27.10.2026", "seller_name": "ООО «КЛИВЭЛ»",
            "client": "Иванов", "payer_name": "Иванов Пётр Сергеевич",
            "address": "Москва", "subject": "Поставка", "signatory": {
                "name": "Иванов Пётр Сергеевич", "position": "Физическое лицо",
                "authority": "От своего имени",
            },
        }
        text = bridge.format_contract_preview(preview)
        self.assertIn("Подписант", text)
        self.assertIn("ФИО: Иванов Пётр Сергеевич", text)
        self.assertIn("Статус: Физическое лицо", text)
        self.assertIn("Действует: От своего имени", text)

        with mock.patch.object(bridge, "current_deal_ui_state", return_value={}), \
             mock.patch.object(bridge, "run_contract_builder", return_value={"ok": True, "preview": preview}), \
             mock.patch.object(bridge, "update_deal_ui_state"), \
             mock.patch.object(bridge, "send_message") as send:
            bridge.prepare_contract_preview("token", "chat", "892")
        labels = {button["text"] for row in send.call_args.args[3]["keyboard"] for button in row}
        self.assertIn("✏️ Исправить подписанта", labels)
        self.assertIn("✏️ Исправить дату", labels)
        self.assertIn("✏️ Исправить адрес", labels)

    def test_deals_navigation_is_a_local_fast_path(self):
        with mock.patch.object(bridge, "update_deal_ui_state") as update_state, \
             mock.patch.object(bridge, "send_message", return_value=True) as send:
            handled = bridge.handle_global_navigation("token", "chat", "🤝 Работа со сделками")
        self.assertTrue(handled)
        update_state.assert_called_once()
        self.assertEqual(send.call_count,1)
        self.assertEqual(send.call_args_list[0],mock.call(
            "token", "chat", "Работа со сделками — выберите действие.", bridge.DEALS_KEYBOARD))

    def test_compact_deal_submenus_are_local_and_contain_only_real_actions(self):
        cases = {
            "🔎 Найти сделку": bridge.DEAL_SEARCH_KEYBOARD,
            "🕘 Последние сделки": bridge.DEAL_RECENT_KEYBOARD,
            "📋 Основное": bridge.DEAL_BASIC_KEYBOARD,
            "📄 Документы сделки": bridge.DEAL_DOCUMENTS_KEYBOARD,
            "📦 Закупка сделки": bridge.DEAL_PROCUREMENT_KEYBOARD,
            "🧰 Монтаж сделки": bridge.DEAL_INSTALLATION_KEYBOARD,
        }
        with mock.patch.object(bridge, "send_message", return_value=True) as send, \
             mock.patch.object(bridge, "run_deal_browser", side_effect=AssertionError("submenu called CRM")):
            for label, menu in cases.items():
                self.assertTrue(bridge.handle_deal_ui("token", "chat", label))
                self.assertEqual(send.call_args.args[3], menu)

    def test_add_payer_button_is_available_only_in_contract_menu(self):
        main_labels = {button["text"] for row in bridge.MAIN_KEYBOARD["keyboard"] for button in row}
        contract_labels = {button["text"] for row in bridge.CONTRACT_KEYBOARD["keyboard"] for button in row}
        self.assertNotIn("🏢 Добавить плательщика", main_labels)
        self.assertIn("🏢 Добавить плательщика", contract_labels)

    def test_legacy_invoice_cost_fields_are_normalized_and_capped(self):
        spec = {"deal_id": "894", "updates": [{
            "offer_id": "13679", "source_line_key": "1", "source_name": "Лоток",
            "source_qty": 96, "source_total": 87436.80, "cost_material": 910.80,
        }]}
        ledger = [{"offer_id": "13679", "qty": 76, "consumed_qty": 0}]
        with mock.patch.object(bridge, "fetch_deal_ledger", return_value=ledger):
            result = bridge.cap_invoice_allocation_to_deal(spec)
        self.assertEqual(76, result["updates"][0]["qty_used"])
        self.assertEqual(69220.80, result["updates"][0]["material_cost_used"])
        self.assertEqual(20, result["unallocated"][0]["qty"])
        self.assertEqual(18216.00, result["unallocated"][0]["amount"])

    def test_repeat_invoice_lines_are_not_turned_into_stock(self):
        spec = {"updates": [{"source_line_key": "ABC", "source_qty": 5,
                              "source_total": 15175, "cost_material": 3035}]}
        status = {"existing": True, "allocated_total": 35595,
                  "source_usage": {"abc": {"qty": 5, "amount": 15175}}}
        result = bridge.trim_previously_allocated_invoice_lines(spec, status)
        self.assertEqual([], result["updates"])
        self.assertEqual(15175, result["_repeat_invoice"]["skipped_amount"])

    def test_distribution_without_current_allocation_does_not_record_empty_deal(self):
        spec = {"deal_id": "894", "updates": [], "unallocated": [{"qty": 2, "amount": 100}],
                "_distribution_plan": {"suggestions": []}}
        self.assertEqual([], bridge.distribution_specs(spec))

    def test_invoice_coverage_requires_unallocated_rows_in_protocol(self):
        incomplete = {"invoice": {"total": 59971}, "updates": [
            {"source_line_key": "a", "source_total": 15175},
            {"source_line_key": "b", "source_total": 6644},
            {"source_line_key": "c", "source_total": 13776},
        ]}
        self.assertEqual(35595, bridge.supplier_invoice_spec_coverage(incomplete))
        incomplete["unallocated"] = [
            {"source_line_key": "d", "amount": 20316},
            {"source_line_key": "e", "amount": 2120},
            {"source_line_key": "f", "amount": 1258},
            {"source_line_key": "g", "amount": 682},
        ]
        self.assertEqual(59971, bridge.supplier_invoice_spec_coverage(incomplete))

    def test_invoice_2507_repeat_remainder_preview_is_24376_and_persists(self):
        spec = {
            "deal_id": "894",
            "invoice": {"number": "2507", "total": 59971},
            "updates": [], "additions": [], "additional_expenses": [],
            "unallocated": [
                {"source_line_key": "a", "qty": 2, "amount": 20316},
                {"source_line_key": "b", "qty": 5, "amount": 2120},
                {"source_line_key": "c", "qty": 2, "amount": 1258},
                {"source_line_key": "d", "qty": 2, "amount": 682},
            ],
        }
        status = {"ok": True, "existing": True, "invoice_total": 59971,
                  "allocated_total": 35595}
        with mock.patch.object(bridge, "run_procurement_workflow",
                               return_value={"ok": False, "error": "нет сопоставлений"}):
            preview, error = bridge.prepare_supplier_invoice_preview(spec, status)
        self.assertIsNone(error)
        self.assertEqual(24376, preview["remaining_after"])
        spec["_allocation_preview"] = preview

        with tempfile.TemporaryDirectory() as folder:
            state_path = os.path.join(folder, "state.json")
            lock_path = os.path.join(folder, "state.lock")
            with open(state_path, "w", encoding="utf-8") as target:
                json.dump({}, target)
            with mock.patch.object(bridge, "DEAL_UI_STATE_FILE", state_path), \
                 mock.patch.object(bridge, "DEAL_UI_STATE_LOCK_FILE", lock_path):
                bridge.enqueue_supplier_invoice_preview("chat", spec)
                stored = bridge.current_deal_ui_state("chat")["supplier_invoice_queue"][0]
        self.assertEqual(24376, stored["_allocation_preview"]["remaining_after"])
        self.assertEqual(24376, sum(x["amount"] for x in stored["unallocated"]))

    def test_old_apply_button_stores_remainder_without_zero_deal_preflight(self):
        spec = {"deal_id": "894", "invoice": {"number": "2507", "total": 59971},
                "updates": [], "additions": [], "additional_expenses": [],
                "unallocated": [{"source_line_key": "a", "qty": 2, "amount": 24376}]}
        state = {"pending": "supplier_invoice_confirm", "current_deal_id": "894",
                 "supplier_invoice_queue": [spec], "supplier_invoice_preview": spec}
        with mock.patch.object(bridge, "current_deal_ui_state", return_value=state), \
             mock.patch.object(bridge, "run_procurement_workflow",
                               return_value={"ok": True, "items": []}) as workflow, \
             mock.patch.object(bridge, "remove_supplier_invoice_preview", return_value=[]), \
             mock.patch.object(bridge, "send_message", return_value=True) as send:
            handled = bridge.handle_deal_ui("token", "chat", "✅ Применить счёт поставщика",
                                            _background=True)
        self.assertTrue(handled)
        self.assertEqual("put_unallocated_stock", workflow.call_args.args[0]["action"])
        self.assertIn("24 376,00", send.call_args.args[2])

    def test_same_supplier_document_has_only_one_active_job(self):
        with tempfile.TemporaryDirectory() as folder:
            jobs_path = os.path.join(folder, "jobs.json")
            lock_path = os.path.join(folder, "jobs.lock")
            source_path = os.path.join(folder, "invoice.pdf")
            with open(source_path, "wb") as source:
                source.write(b"invoice-content")
            with mock.patch.object(bridge, "DOCUMENT_JOBS_FILE", jobs_path), \
                 mock.patch.object(bridge, "DOCUMENT_JOBS_LOCK_FILE", lock_path):
                first = bridge.create_document_job("chat", "861", source_path, "invoice.pdf")
                duplicate = bridge.create_document_job("chat", "861", source_path, "invoice-copy.pdf")
                with open(jobs_path, encoding="utf-8") as source:
                    jobs = json.load(source)
        self.assertFalse(first.get("deduplicated", False))
        self.assertTrue(duplicate["deduplicated"])
        self.assertEqual(first["id"], duplicate["id"])
        self.assertEqual(1, len(jobs))

    def test_ledger_is_synced_once_within_one_worker(self):
        bridge.DEAL_LEDGER_CACHE.clear()
        live = {"ok": True, "ledger": [{"offer_id": "1", "name": "Кабель"}]}
        local = [{"offer_id": "stale"}]
        completed = mock.Mock(return_value=mock.Mock(returncode=0, stdout=json.dumps(live), stderr=""))
        with mock.patch.object(bridge, "_run_deal_ledger_cli", return_value=local) as read_local, \
             mock.patch.object(bridge.subprocess, "run", completed), \
             mock.patch.object(bridge, "record_operation_timing"):
            first = bridge.fetch_deal_ledger("861")
            second = bridge.fetch_deal_ledger("861")
        self.assertEqual(first, second)
        self.assertEqual(1, completed.call_count)
        self.assertEqual(0, read_local.call_count)  # Only verified live rows authorize invoice matching.

    def test_unallocated_rows_can_be_prepared_as_misc_cost(self):
        spec = {"deal_id": "894", "invoice": {"number": "2507", "total": 59971},
                "updates": [], "additions": [], "additional_expenses": [],
                "unallocated": [{"source_line_key": "a", "name": "XT1B", "qty": 2, "amount": 20316},
                                {"source_line_key": "b", "name": "S201", "qty": 5, "amount": 4060}]}
        state = {"pending": "supplier_invoice_confirm", "current_deal_id": "894",
                 "supplier_invoice_queue": [spec], "supplier_invoice_preview": spec}
        preview = {"ok": True, "existing": True, "allocation_amount": 24376,
                   "remaining_after": 0}
        with mock.patch.object(bridge, "current_deal_ui_state", return_value=state), \
             mock.patch.object(bridge, "run_procurement_workflow", return_value={"ok": True}), \
             mock.patch.object(bridge, "prepare_supplier_invoice_preview", return_value=(preview, None)), \
             mock.patch.object(bridge, "update_deal_ui_state") as update, \
             mock.patch.object(bridge, "send_message", return_value=True) as send:
            handled = bridge.handle_deal_ui("token", "chat", "🧾 В прочую себестоимость сделки",
                                            _background=True)
        self.assertTrue(handled)
        saved = update.call_args.kwargs["supplier_invoice_queue"][0]
        self.assertEqual([], saved["unallocated"])
        self.assertEqual(24376, sum(x["amount"] for x in saved["additional_expenses"]))
        self.assertEqual("supplier_misc_confirm", update.call_args.kwargs["pending"])
        self.assertIn("24 376,00", send.call_args.args[2])

    def test_misc_cost_confirmation_applies_and_recalculates(self):
        spec = {"deal_id": "894", "invoice": {"number": "2507"}, "updates": [],
                "additional_expenses": [{"source_line_key": "a", "amount": 24376}]}
        state = {"pending": "supplier_misc_confirm", "current_deal_id": "894",
                 "supplier_invoice_queue": [spec], "supplier_invoice_preview": spec}
        with mock.patch.object(bridge, "current_deal_ui_state", return_value=state), \
             mock.patch.object(bridge, "apply_distributed_invoice_spec",
                               return_value={"ok": True}) as apply, \
             mock.patch.object(bridge, "remove_supplier_invoice_preview", return_value=[]), \
             mock.patch.object(bridge, "send_message", return_value=True) as send:
            handled = bridge.handle_deal_ui("token", "chat", "✅ Подтвердить прочую себестоимость",
                                            _background=True)
        self.assertTrue(handled)
        apply.assert_called_once_with(spec)
        self.assertIn("24 376,00", send.call_args.args[2])

    def test_manual_mapping_turns_selected_remainder_into_deal_update(self):
        source = {"source_line_key": "a", "source_sku": "ABB-A", "name": "Автомат",
                  "qty": 2, "amount": 20316}
        target = {"offer_id": "10", "offer_row_id": "20", "name": "Аппарат защиты",
                  "qty": 1, "available": 1}
        spec = {"deal_id": "894", "invoice": {"number": "2507", "total": 59971},
                "updates": [], "additions": [], "additional_expenses": [],
                "unallocated": [source]}
        state = {"pending": "supplier_manual_mapping", "current_deal_id": "894",
                 "supplier_invoice_queue": [spec], "supplier_invoice_preview": spec,
                 "supplier_mapping_sources": [source], "supplier_mapping_targets": [target]}
        preview = {"ok": True, "allocation_amount": 20316, "remaining_after": 4060}
        with mock.patch.object(bridge, "current_deal_ui_state", return_value=state), \
             mock.patch.object(bridge, "run_procurement_workflow", return_value={"ok": True}), \
             mock.patch.object(bridge, "prepare_supplier_invoice_preview", return_value=(preview, None)), \
             mock.patch.object(bridge, "update_deal_ui_state") as update, \
             mock.patch.object(bridge, "send_message", return_value=True):
            handled = bridge.handle_deal_ui("token", "chat", "1=1", _background=True)
        self.assertTrue(handled)
        saved = update.call_args.kwargs["supplier_invoice_queue"][0]
        self.assertEqual(1, len(saved["unallocated"]))
        self.assertEqual(1, saved["unallocated"][0]["qty"])
        self.assertEqual(10158, saved["unallocated"][0]["amount"])
        self.assertEqual("10", saved["updates"][0]["offer_id"])
        self.assertEqual(10158, saved["updates"][0]["material_cost_used"])

    def test_supplier_protocol_is_blocked_without_fresh_procurement_document(self):
        stale = {"deal_id": "894", "invoice": {"number": "old"}}
        self.assertIsNone(bridge.accept_supplier_invoice_protocol(stale, False))
        self.assertIs(stale, bridge.accept_supplier_invoice_protocol(stale, True))

    def test_supplier_button_repairs_stale_pending_and_never_falls_to_model(self):
        source = {"source_line_key": "a", "name": "XT1B", "qty": 2, "amount": 20316}
        spec = {"deal_id": "894", "invoice": {"number": "2507"}, "unallocated": [source]}
        state = {"pending": "procurement_menu", "current_deal_id": "894",
                 "supplier_invoice_queue": [spec], "supplier_invoice_preview": spec}
        ledger = [{"offer_id": "1", "offer_row_id": "2", "name": "Автомат ABB",
                   "qty": 1, "consumed_qty": 0, "cost_material": 100}]
        with mock.patch.object(bridge, "current_deal_ui_state", return_value=state), \
             mock.patch.object(bridge, "fetch_deal_ledger", return_value=ledger), \
             mock.patch.object(bridge, "update_deal_ui_state") as update, \
             mock.patch.object(bridge, "send_message", return_value=True) as send:
            handled = bridge.handle_deal_ui("token", "chat", "🔗 Сопоставить с позицией сделки",
                                            _background=True)
        self.assertTrue(handled)
        self.assertGreaterEqual(update.call_count, 2)
        self.assertIn("XT1B", send.call_args.args[2])
        self.assertIn("Автомат ABB", send.call_args.args[2])

    def test_confirmed_email_payment_creates_finance_operations_once(self):
        candidate = {"id": "mail1", "exact": True, "payment_number": "140", "status":"pending"}
        state = {"pending": "email_payment_confirm", "email_payment_candidate_id": "mail1"}
        finance_result = {"ok": True, "operations": [
            {"operation_id": "501", "invoice_number": "79566", "amount": 167011.20},
            {"operation_id": "502", "invoice_number": "79567", "amount": 84681.17},
        ]}
        def monitor(payload):
            if payload["action"] == "get": return {"ok": True, "candidate": candidate}
            return {"ok": True}
        with mock.patch.object(bridge, "current_deal_ui_state", return_value=state), \
             mock.patch.object(bridge, "run_email_payment_monitor", side_effect=monitor), \
             mock.patch.object(bridge, "run_megaplan_finance", return_value=finance_result) as finance, \
             mock.patch.object(bridge, "update_deal_ui_state"), \
             mock.patch.object(bridge, "send_message", return_value=True) as send:
            handled = bridge.handle_bank_ui("token", "chat", "✅ Создать расходные операции",
                                            _background=True)
        self.assertTrue(handled)
        finance.assert_called_once_with({"action": "create", "candidate": candidate})
        self.assertIn("операция №501", send.call_args.args[2])
        self.assertIn("операция №502", send.call_args.args[2])

    def test_installation_prepare_never_transfers_before_manager_approval(self):
        prepared={"ok":True,"result":{"deal_id":"894","client":"JetCar","essence":"электроснабжение 6-й эт НК",
            "address":"Москва","contact_name":"","contact_phone":"","installer_name":"Деревянко Сергей",
            "works":[{"planned_qty":1,"rate":1000}],"workbook":"/tmp/test.xlsx"}}
        with mock.patch.object(bridge,"run_installation_workflow",return_value=prepared) as workflow, \
             mock.patch.object(bridge,"update_deal_ui_state") as update, \
             mock.patch.object(bridge,"send_message",return_value=True), \
             mock.patch.object(bridge,"send_document",return_value=True):
            bridge.prepare_installation_after_transition("token","manager","894")
        workflow.assert_called_once_with({"action":"prepare","deal_id":"894","actor":"manager"})
        self.assertEqual("installation_draft_review",update.call_args.kwargs["pending"])

    def test_confirmed_bank_expense_can_reduce_installer_debt(self):
        state={"pending":"bank_installer_payment_confirm","bank_installer_deal_id":"894",
               "bank_installer_transaction":{"id":"tx1","amount":10000,"date":"2026-09-26","purpose":"монтаж"}}
        with mock.patch.object(bridge,"current_deal_ui_state",return_value=state), \
             mock.patch.object(bridge,"run_installation_workflow",return_value={"ok":True,"result":{"debt":5000}}) as workflow, \
             mock.patch.object(bridge,"update_deal_ui_state"), \
             mock.patch.object(bridge,"send_message",return_value=True):
            handled=bridge.handle_bank_ui("token","manager","✅ Учесть как выплату монтажнику",_background=True)
        self.assertTrue(handled)
        self.assertEqual("record_payment",workflow.call_args.args[0]["action"])
        self.assertEqual("bank",workflow.call_args.args[0]["source"])

    def test_manual_supplier_mapping_can_split_one_source_line_proportionally(self):
        spec={"updates":[],"unallocated":[]}
        sources=[{"source_line_key":"cable","name":"Кабель", "qty":10, "amount":1000}]
        targets=[{"offer_id":"a","offer_row_id":"1","name":"Кабель А", "available":6},
                 {"offer_id":"b","offer_row_id":"2","name":"Кабель Б", "available":4}]
        result, lines=bridge.apply_manual_supplier_mapping(spec,sources,targets,[("1","1"),("1","2")])
        self.assertEqual(2,len(result["updates"]))
        self.assertEqual([6,4],[row["qty_used"] for row in result["updates"]])
        self.assertEqual([600,400],[row["material_cost_used"] for row in result["updates"]])
        self.assertEqual([],result["unallocated"])
        self.assertEqual(2,len(lines))

    def test_manual_supplier_mapping_keeps_unmatched_remainder(self):
        spec={"updates":[],"unallocated":[]}
        sources=[{"source_line_key":"cable","name":"Кабель", "qty":10, "amount":1000}]
        targets=[{"offer_id":"a","offer_row_id":"1","name":"Кабель А", "available":6}]
        result,_=bridge.apply_manual_supplier_mapping(spec,sources,targets,[("1","1")])
        self.assertEqual(600,result["updates"][0]["material_cost_used"])
        self.assertEqual(4,result["unallocated"][0]["qty"])
        self.assertEqual(400,result["unallocated"][0]["amount"])


if __name__ == "__main__": unittest.main()
