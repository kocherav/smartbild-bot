"""Owner 20.11: «по таблице» that closes the statement needs no table file."""
import copy
import unittest
from unittest.mock import patch

import bridge
import installer_table_waiver as waiver

STATEMENT = {'deal_id': '861', 'plan_total': 30000.0, 'remaining_total': 18000.0, 'rows': [
    {'work_item_id': 1, 'name': 'Монтаж внутреннего блока', 'unit': 'шт', 'planned_qty': 2, 'rate': 6000,
     'accepted_qty': 2, 'remaining_qty': 0, 'remaining_amount': 0},
    {'work_item_id': 2, 'name': 'Трасса', 'unit': 'м', 'planned_qty': 20, 'rate': 900,
     'accepted_qty': 0, 'remaining_qty': 20, 'remaining_amount': 18000}]}


def session(*lines):
    exceptions = [{'id': n, 'object': obj, 'source': f'По таблице-{amount}', 'amount': amount, 'deal_id': deal,
                   'type': 'table', 'reason': 'нужно выбрать способ учёта ведомости'}
                  for n, (obj, deal, amount) in enumerate(lines, 1)]
    return {'source_path': '/tmp/report.pdf', 'exceptions': exceptions, 'required_tables': len(exceptions),
            'table_requests': [{'object': e['object'], 'source': e['source'], 'deal_id': e['deal_id']} for e in exceptions],
            'objects': [], 'report_lines': []}


def remaining(statements):
    return lambda deal_id: copy.deepcopy(statements.get(deal_id))


class WaiverRules(unittest.TestCase):
    def test_amount_equal_to_the_open_remainder_is_100_percent_without_a_file(self):
        s = session(('Кондиционирование', '861', 18000))
        waived = waiver.waive(s, remaining({'861': STATEMENT}))
        self.assertEqual(1, len(waived))
        self.assertEqual(0, s['required_tables'])
        item = s['exceptions'][0]
        self.assertTrue(item['table_waived'])
        self.assertTrue(item['resolution'])
        # Only what is still open is accrued, item by item, from the statement itself.
        self.assertEqual([(1, 0), (2, 20)], [(r['work_item_id'], r['current_qty']) for r in item['table_rows']])
        self.assertEqual(18000, sum(r['current_amount'] for r in item['table_rows']))

    def test_partial_amount_still_needs_the_table(self):
        s = session(('Кондиционирование', '861', 9000))
        self.assertEqual([], waiver.waive(s, remaining({'861': STATEMENT})))
        self.assertEqual(1, s['required_tables'])

    def test_line_without_a_deal_or_without_a_statement_still_needs_the_table(self):
        s = session(('Неизвестно', None, 18000), ('Отопление', '900', 18000))
        waiver.waive(s, remaining({'861': STATEMENT}))
        self.assertEqual(2, s['required_tables'])

    def test_two_lines_cannot_both_close_the_same_statement(self):
        s = session(('Кондиционирование', '861', 18000), ('Кондиционирование 2', '861', 18000))
        waiver.waive(s, remaining({'861': STATEMENT}))
        self.assertEqual(1, s['required_tables'])

    def test_only_mismatching_lines_are_requested(self):
        s = session(('Кондиционирование', '861', 18000), ('Отопление', '900', 5000))
        waiver.waive(s, remaining({'861': STATEMENT, '900': dict(STATEMENT, deal_id='900', remaining_total=7000)}))
        self.assertEqual([{'object': 'Отопление', 'source': 'По таблице-5000', 'deal_id': '900'}], s['table_requests'])
        self.assertIn('сделка №861 — 100 % по ведомости', waiver.waived_text(s))


    def test_generated_rows_pass_the_acceptance_plan_without_review(self):
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'megaplan-crm'))
        import legacy_report_plan
        s = session(('Кондиционирование', '861', 18000))
        waiver.waive(s, remaining({'861': STATEMENT}))
        works = {'861': [{'id': r['work_item_id'], 'name': r['name'], 'unit': r['unit'], 'planned_qty': r['planned_qty'],
                          'rate': r['rate'], 'accepted_qty': r['accepted_qty']} for r in STATEMENT['rows']]}
        plan = legacy_report_plan.plan(s, works)
        self.assertTrue(plan['ready']); self.assertEqual([], plan['review'])
        self.assertEqual(18000, float(plan['total']))
        works['861'][1]['accepted_qty'] = 5  # more accepted before the manager approved
        self.assertTrue(legacy_report_plan.plan(s, works)['review'], 'остаток изменился — пересчёт, не двойное начисление')


class BridgeFlow(unittest.TestCase):
    def run_report(self, s, statements):
        sent = []
        with patch.object(bridge, 'run_installer_report_intake', return_value={'ok': True, 'session': s}), \
             patch.object(bridge, 'installation_remaining', side_effect=remaining(statements)), \
             patch.object(bridge, 'update_deal_ui_state') as update, \
             patch.object(bridge, 'send_message', side_effect=lambda *a, **k: sent.append(a[2])):
            bridge.process_installer_report('t', 'chat', '/tmp/report.pdf')
        return update.call_args.kwargs['pending'], '\n'.join(sent)

    def test_report_closing_the_statement_goes_straight_to_object_check(self):
        pending, text = self.run_report(session(('Кондиционирование', '861', 18000)), {'861': STATEMENT})
        self.assertEqual('installer_report_objects', pending)
        self.assertIn('100 % по ведомости, файл не нужен', text)
        self.assertNotIn('Пришлите', text)

    def test_only_the_mismatching_table_is_requested(self):
        pending, text = self.run_report(session(('Кондиционирование', '861', 18000), ('Отопление', '900', 5000)),
                                        {'861': STATEMENT})
        self.assertEqual('installer_report_tables', pending)
        self.assertIn('Пришлите 1 соответствующих Excel-файла', text)
        self.assertIn('Отопление', text)

    def test_report_already_waiting_for_tables_can_be_finished_without_them(self):
        # The report stuck on 20.11: five tables requested, the installer sent the partial ones.
        waiting = session(('Кондиционирование', '861', 18000))
        waiting['table_paths'] = []
        sent = []
        with patch.object(bridge, 'run_installer_report_intake', return_value={'ok': True, 'session': copy.deepcopy(waiting)}), \
             patch.object(bridge, 'installation_remaining', side_effect=remaining({'861': STATEMENT})), \
             patch.object(bridge, 'update_deal_ui_state') as update, \
             patch.object(bridge, 'send_message', side_effect=lambda *a, **k: sent.append(a[2])):
            bridge.finish_installer_report_files('t', 'chat', waiting)
        self.assertEqual('installer_report_objects', update.call_args.kwargs['pending'])
        self.assertIn('100 % по ведомости', '\n'.join(sent))


if __name__ == '__main__':
    unittest.main()
