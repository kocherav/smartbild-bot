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


if __name__ == '__main__': unittest.main()
