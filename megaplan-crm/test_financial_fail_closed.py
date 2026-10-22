import json
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
import financial_amounts as fa


class FinancialValidationTest(unittest.TestCase):
    def test_invalid_cost_does_not_become_zero(self):
        for value in ('?', 'NaN', 'inf', float('nan')):
            with patch.object(fa, 'load_overrides', return_value={'overrides': {}}):
                with self.assertRaises(ValueError):
                    fa.component_values('1', {'qty': 2, 'cost_work': value}, 'cost_work')

    def test_unknown_basis_does_not_multiply(self):
        with patch.object(fa, 'load_overrides', return_value={'overrides': {}}):
            with self.assertRaises(ValueError):
                fa.component_values('1', {'qty': 158, 'cost_work': 120000, 'cost_work_basis': 'unknown'}, 'cost_work')

    def test_corrupt_override_is_not_ignored(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'registry.json'; target.write_text('{broken')
            with patch.object(fa, 'OVERRIDES_PATH', str(target)):
                with self.assertRaises(json.JSONDecodeError): fa.load_overrides()

    def test_explicit_line_total_is_not_multiplied(self):
        with patch.object(fa, 'load_overrides', return_value={'overrides': {}}):
            result = fa.component_values('1', {'qty': 158, 'cost_work': 120000, 'cost_work_basis': 'line_total'}, 'cost_work')
        self.assertEqual(120000, result['line_total'])


if __name__ == '__main__': unittest.main()
