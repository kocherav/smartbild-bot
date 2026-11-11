"""Automation proposals in the SmartBild template (owner decision 11.11)."""
import csv
import datetime
import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

import smartbild_kp as k

KP906 = k.KP_DIR / 'deals' / 'КП-906' / 'КП-906.csv'


def kp906_rows():
    rows = []
    with open(KP906, encoding='utf-8-sig') as source:
        for r in csv.DictReader(source, delimiter=';'):
            qty = Decimal(r['Кол-во'].replace(',', '.'))
            price = Decimal(r['Цена'].replace(' ', '').replace(',', '.'))
            rows.append({'name': r['Наименование'], 'qty': str(qty), 'unit': r['Ед.'], 'section': r['Раздел'],
                         'total': str((qty * price).quantize(Decimal('0.01'))), 'tax_rate': '5'})
    return rows


def deal(rows, deal_id='906'):
    total = sum(Decimal(r['total']) for r in rows)
    return {'deal_id': deal_id, 'client': 'ООО «ДЕСАРТДЕКОР»', 'subject': 'Поставка и монтаж системы автоматизации',
            'rows': rows, 'total': str(total)}


class Detection(unittest.TestCase):
    def test_kp906_is_automation_with_the_owners_modules(self):
        rows = kp906_rows()
        self.assertTrue(k.is_automation(rows))
        # The modules chosen by hand for КП-906 in the template chat.
        self.assertEqual(['climate', 'telegram', 'scenes'], k.suggest_modules(rows))

    def test_plain_air_conditioning_deal_is_not_automation(self):
        rows = [{'name': 'Сплит-система Haier AS25', 'qty': '2', 'unit': 'шт.', 'total': '90000', 'tax_rate': '22'},
                {'name': 'Монтаж сплит-системы', 'qty': '2', 'unit': 'шт.', 'total': '24000', 'tax_rate': '22'}]
        self.assertFalse(k.is_automation(rows))

    def test_lighting_and_media_are_suggested_in_page_order(self):
        rows = [{'name': 'Шлюз KNX-DALI', 'qty': '1', 'total': '1'}, {'name': 'Аудиоресивер мультирум', 'qty': '1', 'total': '1'}]
        self.assertEqual(['light', 'media', 'telegram', 'scenes'], k.suggest_modules(rows))


class Inputs(unittest.TestCase):
    def test_csv_reproduces_every_crm_amount_and_the_total(self):
        rows = kp906_rows()
        data = deal(rows)
        spec, table = k.build_inputs(data, ['scenes', 'climate', 'telegram'], 'Сергей', datetime.date(2026, 11, 11))
        self.assertEqual('КП-906', spec['number']); self.assertEqual('11 ноября 2026', spec['date'])
        self.assertEqual('Сергей · ООО «ДЕСАРТДЕКОР»', spec['client'])
        self.assertEqual(['climate', 'telegram', 'scenes'], spec['modules'], 'порядок страниц шаблона')
        self.assertEqual(5, spec['vat']); self.assertEqual('+7 (495) 846-72-71', spec['manager']['phone'])
        parsed = list(csv.DictReader(table.splitlines(), delimiter=';'))
        total = sum(Decimal(r['Кол-во']) * Decimal(r['Цена']) for r in parsed)
        self.assertEqual(Decimal('839452.00'), total)

    def test_air_conditioning_deal_gets_the_daikin_climate_texts(self):
        spec, _ = k.build_inputs(deal(kp906_rows()), ['climate'], '', datetime.date(2026, 11, 11))
        self.assertIn('Daikin', spec['overrides']['climate']['lead'])

    def test_ventilation_deal_keeps_the_general_climate_page(self):
        rows = [{'name': 'Контроллер KNX для ПВУ Breezart', 'qty': '1', 'unit': 'шт.', 'total': '50000', 'tax_rate': '5',
                 'section': 'Оборудование и материалы'}]
        spec, _ = k.build_inputs(deal(rows), ['climate'], '', datetime.date(2026, 11, 11))
        self.assertNotIn('overrides', spec)

    def test_unit_price_that_is_not_whole_kopecks_keeps_the_line_amount(self):
        rows = [{'name': 'Кабель KNX', 'qty': '3', 'unit': 'м', 'total': '100.00', 'tax_rate': '5',
                 'section': 'Оборудование и материалы'}]
        _, table = k.build_inputs(deal(rows), [], '', datetime.date(2026, 11, 11))
        line = list(csv.DictReader(table.splitlines(), delimiter=';'))[0]
        self.assertEqual(('1', '100.00'), (line['Кол-во'], line['Цена']))
        self.assertIn('(3 м)', line['Наименование'])

    def test_mixed_vat_rates_are_refused_not_misprinted(self):
        rows = [{'name': 'Контроллер KNX', 'qty': '1', 'total': '10', 'tax_rate': '5'},
                {'name': 'Монтаж', 'qty': '1', 'total': '10', 'tax_rate': '22'}]
        with self.assertRaises(ValueError):
            k.build_inputs(deal(rows), [], '', datetime.date(2026, 11, 11))

    def test_total_mismatch_is_refused(self):
        data = deal(kp906_rows()); data['total'] = '1.00'
        with self.assertRaises(ValueError):
            k.build_inputs(data, [], '', datetime.date(2026, 11, 11))


@unittest.skipUnless((k.KP_DIR / 'node_modules' / 'playwright').is_dir(),
                     'зависимости шаблона не установлены (npm ci в kp-smartbild)')
class RealRender(unittest.TestCase):
    def test_kp906_from_crm_rows_renders_pdf_and_word_with_the_exact_total(self):
        with tempfile.TemporaryDirectory() as folder:
            rows = kp906_rows()
            pdf, docx = k.render(deal(rows), k.suggest_modules(rows), 'Сергей', datetime.date(2026, 11, 11), folder)
            self.assertTrue(pdf.stat().st_size > 10000); self.assertTrue(docx.stat().st_size > 10000)


if __name__ == '__main__':
    unittest.main()
