import json, os, tempfile, unittest
from openpyxl import Workbook
from historical_installation_migration import parse_workbook, registry_plan

class HistoricalMigrationTests(unittest.TestCase):
    def test_retired_mass_history_and_name_merge_never_touch_database(self):
        from unittest.mock import patch
        import historical_installation_migration as migration
        with patch.object(migration.iw,'connect') as db,patch.object(migration,'MegaplanAPI') as api:
            with self.assertRaises(ValueError):migration.mark_registry_migrations_historical()
            with self.assertRaises(ValueError):migration.reconcile_full_scope('1')
            db.assert_not_called();api.assert_not_called()
    def test_parses_detail_and_keeps_standalone_extra_once(self):
        fd,path=tempfile.mkstemp(suffix='.xlsx'); os.close(fd)
        try:
            wb=Workbook(); ws=wb.active
            ws.append(['№','Объект','Исходная строка','Тип','Кол-во','Ед.','Расценка','Сумма'])
            ws.append([1,'x','По таблице-100','Работа по таблице','','','',100])
            ws.append([2,'x','Штроба','Работа','','','',15])
            ws.append([]); ws.append(['№','Позиция монтажной ведомости','Ед.','План, кол-во','Расценка','Плановая сумма','Закрыто ранее','Закрыто сейчас','Сумма отчёта'])
            ws.append([1,'Кабель','м',100,1,100,0,100,100])
            wb.save(path)
            parsed=parse_workbook(path)
            self.assertEqual(115, parsed['total']); self.assertEqual(1,len(parsed['details'])); self.assertEqual(1,len(parsed['extras']))
            self.assertEqual('м', parsed['details'][0]['unit'])
        finally: os.unlink(path)

    def test_registry_plan_preserves_approved_rows_and_rejects_bad_totals(self):
        fd, path = tempfile.mkstemp(suffix='.json'); os.close(fd)
        try:
            with open(path, 'w', encoding='utf-8') as output:
                json.dump({'reports': [{
                    'id': 'report-1', 'date': '10.08.2026',
                    'excel_path': '/archive/report.xlsx',
                    'deals': [{'deal_id': '864', 'amount': 12000, 'rows': [
                        {'source': 'Монтаж блока', 'amount': 7000},
                        {'source': 'Такелаж', 'amount': 5000},
                    ]}],
                }]}, output, ensure_ascii=False)
            plan = registry_plan('864', path)
            self.assertEqual(1, plan['report_count'])
            self.assertEqual(12000, plan['accepted_total'])
            self.assertEqual('registry:report-1:deal-864', plan['reports'][0]['external_id'])
            with open(path, 'w', encoding='utf-8') as output:
                json.dump({'reports': [{
                    'id': 'bad', 'date': '10.08.2026',
                    'deals': [{'deal_id': '864', 'amount': 13000,
                               'rows': [{'source': 'Монтаж', 'amount': 7000}]}],
                }]}, output, ensure_ascii=False)
            with self.assertRaisesRegex(ValueError, 'не сходится'):
                registry_plan('864', path)
        finally:
            os.unlink(path)
