import unittest
from unittest.mock import patch
import deal_creation
import bridge


class ReviewTest(unittest.TestCase):
    def spec(self):
        return {'client_id': '42', 'client_name': 'Example', 'description': 'Lighting',
                'tax_mode': 'none', 'items': [{'name': 'Cable', 'qty': 2, 'unit_price': 12.34}]}

    def test_review_includes_identity_and_total(self):
        result = deal_creation.review(self.spec())
        self.assertIn('ID 42', result); self.assertIn('24,68', result)

    def test_review_uses_russian_number_format(self):
        spec = self.spec(); spec['items'] = [{'name': 'Split', 'qty': 2.0, 'unit_price': 52000}]
        result = deal_creation.review(spec)
        self.assertIn('Split — 2 × 52 000,00 = 104 000,00 ₽', result)
        self.assertIn('Итого по позициям: 104 000,00 ₽.', result)

    def test_discount_cannot_be_silently_ignored_or_applied_twice(self):
        spec=self.spec(); spec['discount_pct']=10
        with self.assertRaises(ValueError): deal_creation.review(spec)
        spec['price_basis']='net'
        self.assertIn('24,68',deal_creation.review(spec))

    def test_line_total_mismatch_is_not_treated_as_unit_price(self):
        spec=self.spec(); spec['items'][0]['total']=12.34
        with self.assertRaises(ValueError): deal_creation.review(spec)

    def test_invalid_numbers_and_missing_prices_rejected(self):
        for value in ('NaN', 'Infinity', -1, None, ''):
            with self.subTest(value=value):
                spec = self.spec(); spec['items'][0]['unit_price'] = value
                with self.assertRaises(ValueError): deal_creation.review(spec)

    def test_zero_quantity_and_unknown_identity_rejected(self):
        spec = self.spec(); spec['items'][0]['qty'] = 0
        with self.assertRaises(ValueError): deal_creation.review(spec)
        spec = self.spec(); spec.pop('client_id')
        with self.assertRaises(ValueError): deal_creation.review(spec)

    def test_no_implicit_additional_work_at_commit(self):
        spec = self.spec(); spec['items'][0]['include_install'] = True
        with self.assertRaises(ValueError): deal_creation.review(spec)

    def test_prepare_only_persists_preview_and_never_creates(self):
        with patch.object(bridge, 'update_deal_ui_state') as state, patch.object(bridge, 'send_message'), patch.object(bridge, 'run_create_megaplan_deal') as create:
            bridge.prepare_deal_creation_review('token', 'actor', self.spec())
        create.assert_not_called()
        self.assertEqual('deal_create_confirm', state.call_args.kwargs['pending'])

    def test_normalization_rejects_nan_and_infinity(self):
        for field in ('qty', 'unit_price'):
            spec = self.spec(); spec['items'][0][field] = float('nan')
            self.assertIsNotNone(bridge.normalize_create_deal_spec(spec)[1])


class ProjectWithoutPrices(unittest.TestCase):
    """Owner 22.11: a project PDF without prices failed with «цена за единицу: требуется число».
    Now the bot looks the prices up in the catalogs before asking for the client."""
    def spec(self):
        return {'client_name': 'Cliwell', 'description': 'Лаврушинский', 'tax_mode': 'none', 'user_request': 'создай сделку',
                'items': [{'name': 'Кондиционер AS25S2SF3FA-B', 'qty': 2}, {'name': 'Труба 6,35', 'qty': 10}]}

    def priced(self, items):
        return {'ok': True, 'found': 1, 'missing': ['Труба 6,35'],
                'items': [{**items[0], 'unit_price': 95000, 'price_source': 'Hogart AS25S2SF3FA-B'},
                          {**items[1], 'unit_price': 0, 'price_source': 'цена не найдена в каталогах'}]}

    def test_prices_are_looked_up_before_the_client_question_and_zero_rows_pass_review(self):
        sent = []
        with patch.object(bridge, 'resolve_missing_prices', side_effect=self.priced) as lookup, \
             patch.object(bridge, 'search_creation_clients', return_value={'ok': True, 'clients': [{'id': '7', 'name': 'Cliwell', 'kind': 'company'}]}), \
             patch.object(bridge, 'update_deal_ui_state') as state, \
             patch.object(bridge, 'send_message', side_effect=lambda t, c, text, *a, **k: sent.append(text)), \
             patch.object(bridge, 'run_create_megaplan_deal') as create, \
             patch('document_tax_policy.creation_rate', return_value='none'):
            bridge.prepare_deal_creation_review('token', 'actor', self.spec())
        lookup.assert_called_once()
        create.assert_not_called()
        self.assertIn('нашёл 1 из 2', sent[1]); self.assertIn('• Труба 6,35', sent[1])
        self.assertEqual('deal_create_confirm', state.call_args.kwargs['pending'])
        self.assertIn('190 000,00', sent[-1]); self.assertIn('⚠️ цена не найдена в каталогах', sent[-1])
        self.assertTrue(state.call_args.kwargs['deal_create_spec']['prices_resolved'])

    def test_lookup_failure_still_lets_the_deal_through_with_zero_prices(self):
        sent = []
        with patch.object(bridge, 'resolve_missing_prices', return_value={'ok': False, 'error': 'TimeoutExpired'}), \
             patch.object(bridge, 'update_deal_ui_state') as state, \
             patch.object(bridge, 'send_message', side_effect=lambda t, c, text, *a, **k: sent.append(text)):
            spec = {**self.spec(), 'client_id': '7'}; spec.pop('user_request')
            with patch('document_tax_policy.creation_rate', return_value='none'):
                bridge.prepare_deal_creation_review('token', 'actor', spec)
        self.assertIn('не сработал', sent[1])
        self.assertEqual('deal_create_confirm', state.call_args.kwargs['pending'])

    def test_priced_specification_is_not_looked_up(self):
        with patch.object(bridge, 'resolve_missing_prices') as lookup, patch.object(bridge, 'update_deal_ui_state'), \
             patch.object(bridge, 'send_message'):
            bridge.prepare_deal_creation_review('token', 'actor', ReviewTest().spec())
        lookup.assert_not_called()


if __name__ == '__main__': unittest.main()
