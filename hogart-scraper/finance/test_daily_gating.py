"""10.11: posting ran on one day of seven in November; the failing step had no cause."""
import subprocess
import unittest
from unittest.mock import patch

import daily


class PostingGateTests(unittest.TestCase):
    def test_review_letters_report_and_sync_errors_do_not_stop_posting(self):
        errors = [{'stage': 'intake_review', 'error': 'письмо от нового отправителя'},
                  {'stage': 'registry_sync', 'error': 'OSError'},
                  {'stage': 'mail', 'error': 'timeout'},
                  {'stage': 'report', 'error': 'CalledProcessError'}]
        self.assertEqual([], daily.posting_blockers(errors))

    def test_import_or_export_failure_stops_posting(self):
        errors = [{'stage': 'intake_review', 'error': 'x'}, {'stage': 'import', 'error': 'bad zip'},
                  {'stage': 'export', 'error': 'ledger'}]
        self.assertEqual(['import', 'export'], [e['stage'] for e in daily.posting_blockers(errors)])

    def test_error_keeps_the_cause_from_stderr(self):
        exc = subprocess.CalledProcessError(1, ['python', 'report.py'],
                                            stderr='Traceback (most recent call last):\n  File "report.py"\n'
                                                   'KeyError: \'НачальныйОстаток\'\n')
        text = daily.error_text(exc)
        self.assertIn('exit status 1', text)
        self.assertIn("KeyError: 'НачальныйОстаток'", text)

    def test_error_text_is_bounded(self):
        exc = subprocess.CalledProcessError(1, ['x'], stderr='строка\n' * 5000)
        self.assertLessEqual(len(daily.error_text(exc)), 1500)

    @patch('daily.subprocess.run')
    def test_daily_projection_precedes_idempotent_procurement_reconciliation(self, run):
        run.side_effect = [
            subprocess.CompletedProcess([], 0, stdout='{"registry_updates": 1}'),
            subprocess.CompletedProcess([], 0, stdout='{"ok": true, "matched": [{"transaction_id": "x"}]}'),
        ]
        result = daily.project_and_reconcile('/test/python')
        self.assertEqual(1, result['registry']['registry_updates'])
        self.assertEqual('reconcile_bank', __import__('json').loads(run.call_args_list[1].kwargs['input'])['action'])
        self.assertIn('bank_registry_projection.py', run.call_args_list[0].args[0][1])
        self.assertIn('procurement_workflow.py', run.call_args_list[1].args[0][1])


if __name__ == '__main__':
    unittest.main()
