import json
from pathlib import Path
import tempfile
import unittest

import kp_eval


class KPEvalTests(unittest.TestCase):
    def test_crm_write_and_delivery_to_a_person_fail_isolation(self):
        receipt = {
            'crm_writes': [{'script': 'create_deal.py', 'action': 'create'}],
            'unexpected_external': [],
            'telegram_chats': ['kp-eval-case', 'real-person'],
            'blocked_writes': [],
        }
        failures = kp_eval.isolation_failures(receipt, 'kp-eval-case')
        self.assertTrue(any('CRM' in item for item in failures))
        self.assertTrue(any('real-person' in item for item in failures))

    def test_tiers_false_removes_g5_from_general_checks(self):
        case = {'id': 'cheap', 'tiers': False, 'checks': ['самый дешёвый']}
        labels = [item['id'] for item in kp_eval.judge_checks(case)]
        self.assertNotIn('G5', labels)
        self.assertEqual(labels, ['G1', 'G2', 'G3', 'G4', 'G6', 'G7', 'G8', 'G9', 'G10', 'check-1'])

    def test_success_percentage_and_summary_have_no_purchase_prices(self):
        cases = [
            {'id': 'ok', 'success': True, 'failed_checks': [], 'turns': 2, 'duration_sec': 1.2},
            {'id': 'bad', 'success': False, 'failed_checks': ['G2'], 'turns': 3,
             'duration_sec': 2.4, 'purchase_price': 123},
            {'id': 'ok2', 'success': True, 'failed_checks': [], 'turns': 1, 'duration_sec': 0.4},
        ]
        summary = kp_eval.build_summary(cases)
        self.assertEqual(summary['success_pct'], 66.67)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            kp_eval.write_summary(output, summary)
            text = (output / 'summary.md').read_text(encoding='utf-8')
        self.assertIn('66.67%', text)
        self.assertNotIn('123', text)

    def test_case_selection_only_limit_and_seed_are_stable(self):
        cases = [{'id': value} for value in ('a', 'b', 'c')]
        one = kp_eval.select_cases(cases, only={'a', 'c'}, limit=1, seed='x')
        two = kp_eval.select_cases(cases, only={'a', 'c'}, limit=1, seed='x')
        self.assertEqual(one, two)
        self.assertEqual(len(one), 1)
        self.assertIn(one[0]['id'], {'a', 'c'})


if __name__ == '__main__':
    unittest.main()
