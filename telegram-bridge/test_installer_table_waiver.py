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


    def test_line_without_a_deal_takes_the_only_statement_with_that_remainder(self):
        # 20.11: all 7 table lines of the stuck report had deal_id=None.
        s = session(('Объект А', None, 18000), ('Объект Б', None, 9000))
        waived = waiver.waive(s, remaining({'861': STATEMENT}), lambda: {'861': 18000, '900': 50000})
        self.assertEqual(['861'], [item['deal_id'] for item in waived])
        self.assertIn('определена по совпадению', waived[0]['reason'])
        self.assertEqual(1, s['required_tables'])
        self.assertIsNone(s['exceptions'][1]['deal_id'])

    def test_two_statements_with_the_same_remainder_are_not_guessed(self):
        s = session(('Объект А', None, 18000))
        waiver.waive(s, remaining({'861': STATEMENT, '862': dict(STATEMENT, deal_id='862')}),
                     lambda: {'861': 18000, '862': 18000})
        self.assertIsNone(s['exceptions'][0]['deal_id'])
        self.assertEqual(1, s['required_tables'])

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


class OwnTableWithoutDeal(unittest.TestCase):
    def test_own_statement_table_finds_its_line_by_amount_when_the_line_has_no_deal(self):
        import installer_report_intake as intake
        import installer_workbook_intake
        own = {'deal_id': '857', 'rows': [], 'column': 'Выполнено', 'total': 150000.0}
        targets = [{'type': 'table', 'deal_id': None, 'amount': 31000, 'source': 'по таблице-31000'},
                   {'type': 'table', 'deal_id': None, 'amount': 150000, 'source': 'по таблице-150000'}]
        book = type('Book', (), {'close': lambda self: None})()
        with patch.object(intake, 'load_workbook', return_value=book), \
             patch.object(installer_workbook_intake, 'read', return_value=own):
            intake.attach_tables(targets, ['/tmp/857.xlsx'])
        self.assertEqual('857', targets[1]['deal_id'])
        self.assertTrue(targets[1]['table_path'])
        self.assertIsNone(targets[0]['deal_id'])

    def test_unmatched_own_table_explains_itself(self):
        import installer_report_intake as intake
        import installer_workbook_intake
        own = {'deal_id': '857', 'rows': [], 'column': 'Выполнено', 'total': 99.0}
        book = type('Book', (), {'close': lambda self: None})()
        with patch.object(intake, 'load_workbook', return_value=book), \
             patch.object(installer_workbook_intake, 'read', return_value=own):
            with self.assertRaisesRegex(ValueError, 'Таблица по сделке №857'):
                intake.attach_tables([{'type': 'table', 'deal_id': None, 'amount': 5}], ['/tmp/857.xlsx'])


class OldFormatTablesByAmount(unittest.TestCase):
    def test_old_tables_go_to_the_lines_with_their_amounts_not_the_first_lines(self):
        # 20.11 dry run: files for 108 200 and 30 000 went to the 150 000 and 20 000 lines.
        import installer_report_intake as intake
        import installer_workbook_intake
        def profile(name, total):
            return {'path': '/tmp/' + name, 'filename': name, 'text': name, 'rows': [], 'calculated_total': total,
                    'completion_columns': [{'column': 9, 'sum': total, 'footer': total}]}
        profiles = {'/tmp/конд.xlsx': profile('конд.xlsx', 30000), '/tmp/вент.xlsx': profile('вент.xlsx', 108200)}
        targets = [{'type': 'table', 'object': o, 'source': f'по таблице-{a}', 'amount': a, 'deal_id': None}
                   for o, a in (('Отопление', 150000), ('Монтаж компрессора', 20000), ('Вентиляция', 108200),
                                ('Кондиционирование', 30000))]
        book = type('Book', (), {'close': lambda self: None})()
        with patch.object(intake, 'load_workbook', return_value=book), \
             patch.object(installer_workbook_intake, 'read', return_value=None), \
             patch.object(intake, 'table_profiles', side_effect=lambda path: [profiles[path]]), \
             patch.object(intake, 'FACT_REGISTRY', '/nonexistent/facts.json'):
            intake.attach_tables(targets, list(profiles))
        got = {t['object']: t.get('table_file') for t in targets}
        self.assertEqual({'Отопление': None, 'Монтаж компрессора': None,
                          'Вентиляция': 'вент.xlsx', 'Кондиционирование': 'конд.xlsx'}, got)
        self.assertTrue(all(t['completion_matches_report'] for t in targets if t.get('table_file')))


class BridgeFlow(unittest.TestCase):
    def run_report(self, s, statements):
        sent = []
        with patch.object(bridge, 'archive_installer_files'), \
             patch.object(bridge, 'run_installer_report_intake', return_value={'ok': True, 'session': s}), \
             patch.object(bridge, 'installation_remaining', side_effect=remaining(statements)), \
             patch.object(bridge, 'installation_open_remainders', return_value={}), \
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
             patch.object(bridge, 'installation_open_remainders', return_value={}), \
             patch.object(bridge, 'update_deal_ui_state') as update, \
             patch.object(bridge, 'send_message', side_effect=lambda *a, **k: sent.append(a[2])):
            bridge.finish_installer_report_files('t', 'chat', waiting)
        self.assertEqual('installer_report_objects', update.call_args.kwargs['pending'])
        self.assertIn('100 % по ведомости', '\n'.join(sent))


if __name__ == '__main__':
    unittest.main()



class TablesStepNeverBlocks(unittest.TestCase):
    """Owner 22.11: Sergey could not upload his tables — the bot answered «лишний файл»."""

    def test_more_tables_are_accepted_after_the_required_count_was_recalculated(self):
        import inspect
        source = inspect.getsource(bridge)
        self.assertNotIn('лишний файл в пакет не добавлен', source)

    def test_skip_button_hands_the_report_over_with_missing_lines_marked(self):
        waiting = session(('Отопление', '857', 150000), ('Компрессор', '890', 18000))
        waiting['table_paths'] = []
        sent = []
        with patch.object(bridge, 'run_installer_report_intake', return_value={'ok': True, 'session': copy.deepcopy(waiting)}), \
             patch.object(bridge, 'installation_remaining', side_effect=remaining({'890': dict(STATEMENT, deal_id='890')})), \
             patch.object(bridge, 'installation_open_remainders', return_value={}), \
             patch.object(bridge, 'update_deal_ui_state') as update, \
             patch.object(bridge, 'send_message', side_effect=lambda *a, **k: sent.append(a[2])):
            bridge.finish_installer_report_files('t', 'inst', waiting, allow_missing=True)
        state = update.call_args.kwargs
        self.assertEqual('installer_report_objects', state['pending'])
        final = state['installer_report']
        heating = [e for e in final['exceptions'] if e['object'] == 'Отопление'][0]
        self.assertTrue(heating['table_missing'])
        self.assertEqual('передано руководителю без таблицы', heating['resolution'])
        self.assertIn('Без таблиц переданы руководителю', '\n'.join(sent))
        self.assertIn(bridge.INSTALLER_SKIP_TABLES, str(bridge.INSTALLER_REPORT_FILES_KEYBOARD))


class TablesInAnyFormat(unittest.TestCase):
    """Owner 22.11: «научи бота принимать таблицы в PDF» (and photos, old .xls)."""

    def test_money_in_pdf_text_is_read_in_russian_formats(self):
        import installer_report_intake as intake
        found = intake.amounts_in_text('Итого: 150 000,00 руб.\nКабель 1 200\nВсего 31000')
        self.assertTrue({150000.0, 1200.0, 31000.0} <= found)

    def test_pdf_with_a_line_total_closes_that_line_for_the_manager(self):
        import installer_report_intake as intake
        targets = [{'type': 'table', 'object': 'Отопление', 'source': 'по таблице-150000', 'amount': 150000},
                   {'type': 'table', 'object': 'Тёплый пол', 'source': 'по таблице-31000', 'amount': 31000}]
        texts = {'/tmp/heat.pdf': 'Отопление ... Итого 150 000,00', '/tmp/other.pdf': 'без сумм'}
        loose = intake.attach_file_tables(targets, list(texts), reader=lambda p: texts[p])
        self.assertEqual('heat.pdf', targets[0]['table_file'])
        self.assertEqual('file', targets[0]['table_kind'])
        self.assertEqual([], targets[0]['table_rows'], 'из файла ничего не начисляется автоматически')
        self.assertIsNone(targets[1].get('table_path'))
        self.assertEqual(['other.pdf'], [x['file'] for x in loose])

    def test_photo_is_kept_as_a_loose_file_not_guessed(self):
        import installer_report_intake as intake
        targets = [{'type': 'table', 'object': 'Шкафы', 'source': 'по таблице-4000', 'amount': 4000}]
        loose = intake.attach_file_tables(targets, ['/tmp/table.jpg'], reader=lambda p: '')
        self.assertEqual(['table.jpg'], [x['file'] for x in loose])

    def test_photos_are_allowed_in_the_tables_step_only(self):
        self.assertTrue(bridge.installer_media_allowed({'photo': []}, 'installer_report_tables'))
        self.assertFalse(bridge.installer_media_allowed({'photo': []}, None))

    def test_broken_xls_is_refused_politely_not_crashed(self):
        import tempfile
        with tempfile.NamedTemporaryFile(suffix='.xls') as broken:
            broken.write(b'not an excel file'); broken.flush()
            self.assertIsNone(bridge.xls_to_xlsx(broken.name))

    def test_manager_gets_file_tables_and_loose_files(self):
        files = bridge.installer_files_for_manager({
            'exceptions': [{'table_kind': 'file', 'table_path': '/tmp/heat.pdf', 'source': 'по таблице-150000'},
                           {'table_path': '/tmp/vent.xlsx', 'source': 'x'}],
            'unmatched_files': [{'file': 'a.jpg', 'path': '/tmp/a.jpg'}]})
        self.assertEqual(['/tmp/heat.pdf', '/tmp/a.jpg'], [p for p, _ in files])


class SergeyFilesOf22November(unittest.TestCase):
    """TASK-20261122-18: his files cover all 7 lines; the matcher must see that."""

    def run_attach(self, targets, profiles):
        import installer_report_intake as intake
        import installer_workbook_intake
        book = type('Book', (), {'close': lambda self: None})()
        with patch.object(intake, 'load_workbook', return_value=book), \
             patch.object(installer_workbook_intake, 'read', return_value=None), \
             patch.object(intake, 'table_profiles', side_effect=lambda path: [profiles[path]]), \
             patch.object(intake, 'FACT_REGISTRY', '/nonexistent/facts.json'):
            return intake.attach_tables(targets, list(profiles))

    @staticmethod
    def row(n, name, amount):
        return {'number': n, 'name': name, 'qty': 1, 'unit': 'шт', 'rate': amount, 'total': amount,
                'extra_values': {'9': amount}}

    def profile(self, name, rows):
        total = sum(r['extra_values']['9'] for r in rows)
        return {'path': '/tmp/' + name, 'filename': name, 'text': name, 'rows': rows, 'calculated_total': total,
                'completion_columns': [{'column': 9, 'sum': total, 'footer': total}]}

    def test_duplicate_heating_and_one_column_for_two_lines(self):
        targets = [{'type': 'table', 'object': o, 'source': f'по таблице-{a}', 'amount': a, 'deal_id': None}
                   for o, a in (('Отопление', 150000), ('Тёплый пол', 31000), ('Шкафы', 4000))]
        profiles = {
            '/tmp/отопление.xlsx': self.profile('отопление.xlsx', [self.row(1, 'Радиаторы', 150000)]),
            '/tmp/22.11.xlsx': self.profile('22.11.xlsx', [self.row(1, 'Шкаф', 4000), self.row(2, 'Мат тёплого пола', 20000),
                                                            self.row(3, 'Терморегулятор', 6000), self.row(4, 'Укладка', 5000)]),
            '/tmp/отопление2.xlsx': self.profile('отопление2.xlsx', [self.row(1, 'Радиаторы', 150000)]),
        }
        loose = self.run_attach(targets, profiles)
        got = {t['object']: (t.get('table_file'), t.get('completion_matches_report'), sum(r['current_amount'] for r in t.get('table_rows') or []))
               for t in targets}
        self.assertEqual({'Отопление': ('отопление2.xlsx', True, 150000),
                          'Тёплый пол': ('22.11.xlsx', True, 31000),
                          'Шкафы': ('22.11.xlsx', True, 4000)}, got)
        self.assertEqual([('отопление.xlsx', 'отопление2.xlsx')], [(x['file'], x['duplicate_of']) for x in loose])

    def test_older_period_column_does_not_steal_another_line(self):
        # TASK-20261122-21 dry run: «22.11.xlsx» had an older 30 000 column and was given to
        # conditioning; warm floor stayed without a table.
        targets = [{'type': 'table', 'object': o, 'source': f'по таблице-{a}', 'amount': a, 'deal_id': None}
                   for o, a in (('Тёплый пол', 31000), ('Шкафы', 4000), ('Кондиционирование', 30000))]
        common = self.profile('22.11.xlsx', [self.row(1, 'Шкаф', 4000), self.row(2, 'Мат', 20000),
                                              self.row(3, 'Терморегулятор', 6000), self.row(4, 'Укладка', 5000)])
        common['completion_columns'].insert(0, {'column': 8, 'sum': 30000, 'footer': 30000})
        cond = self.profile('кондиционирование 20.11.xlsx', [self.row(1, 'Сплит', 30000)])
        loose = self.run_attach(targets, {'/tmp/кондиционирование 20.11.xlsx': cond, '/tmp/22.11.xlsx': common})
        got = {t['object']: t.get('table_file') for t in targets}
        self.assertEqual({'Тёплый пол': '22.11.xlsx', 'Шкафы': '22.11.xlsx',
                          'Кондиционирование': 'кондиционирование 20.11.xlsx'}, got)
        self.assertEqual([], loose)

    def test_ambiguous_split_is_not_guessed(self):
        import installer_report_intake as intake
        profile = self.profile('x.xlsx', [self.row(1, 'a', 5000), self.row(2, 'b', 5000)])
        targets = [{'amount': 5000}, {'amount': 5000}]
        self.assertIsNone(intake.split_rows(profile, '9', targets), 'два одинаковых способа — не угадываем')


class WorkbookWithSeveralSheets(unittest.TestCase):
    def test_each_sheet_is_its_own_table(self):
        import os, tempfile
        from openpyxl import Workbook
        import installer_report_intake as intake
        with tempfile.TemporaryDirectory() as folder:
            book = Workbook()
            cond = book.active; cond.title = 'Кондиционирование'
            cond.append(['№', 'Работа', 'Ед', 'План', 'Цена', 'Всего', 'Период 1', 'Период 2'])
            cond.append([1, 'Монтаж сплита', 'шт', 1, 30000, 30000, None, 30000])
            cond.append(['Итого', None, None, None, None, None, None, 30000])
            el = book.create_sheet('Электрика')
            el.append(['№', 'Работа', 'Ед', 'План', 'Цена', 'Всего', 'Период 1', 'Период 2'])
            for n, (name, amount) in enumerate((('Шкаф', 4000), ('Мат тёплого пола', 20000),
                                                ('Терморегулятор', 6000), ('Укладка', 5000)), 1):
                el.append([n, name, 'шт', 1, amount, amount, None, amount])
            el.append(['Итого', None, None, None, None, None, None, 35000])
            path = os.path.join(folder, '22.11.xlsx'); book.save(path); book.close()
            targets = [{'type': 'table', 'object': o, 'source': f'по таблице-{a}', 'amount': a, 'deal_id': None}
                       for o, a in (('Тёплый пол', 31000), ('Шкафы', 4000), ('Кондиционирование', 30000))]
            with patch.object(intake, 'FACT_REGISTRY', os.path.join(folder, 'facts.json')):
                loose = intake.attach_tables(targets, [path])
        got = {t['object']: (t.get('table_file'), round(sum(r['current_amount'] for r in t.get('table_rows') or [])))
               for t in targets}
        self.assertEqual({'Тёплый пол': ('22.11.xlsx / Электрика', 31000), 'Шкафы': ('22.11.xlsx / Электрика', 4000),
                          'Кондиционирование': ('22.11.xlsx / Кондиционирование', 30000)}, got)
        self.assertEqual([], loose)


class InstallerFilesGoToOneDrive(unittest.TestCase):
    """Owner 22.11: Sergey's files were not in OneDrive — every report file is archived on receipt."""

    def test_files_are_archived_in_background_with_installer_date_and_kind(self):
        calls = []
        with patch.object(bridge, 'run_background_job', side_effect=lambda job, *a, **k: job()), \
             patch.object(bridge, 'run_installation_workflow', side_effect=lambda spec: calls.append(spec) or {'ok': True}):
            bridge.archive_installer_files('t', 'inst', ['/tmp/отопление.xlsx', None], '20.11.2026', 'Таблицы')
        self.assertEqual([{'action': 'archive_upload', 'path': '/tmp/отопление.xlsx', 'kind': 'Таблицы',
                           'installer_name': bridge.INSTALLER_ARCHIVE_NAME, 'report_date': '20.11.2026'}], calls)

    def test_archive_path_in_onedrive(self):
        import sys, tempfile
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'megaplan-crm'))
        import installation_workflow as iw
        with tempfile.NamedTemporaryFile(suffix='.pdf') as f, patch.object(iw, 'rclone_copy') as copy:
            result = iw.archive_installer_upload(f.name, 'Сергей Деревянко', '20.11.2026', 'Таблицы')
        self.assertTrue(result['remote'].startswith('onedrive:SmartBild/Монтажи/Отчёты монтажников/'
                                                     'Сергей Деревянко/20.11.2026/Таблицы/'))
        copy.assert_called_once()
