"""Owner 24.11: rows of supplier invoices read from their text, only when qty × price = amount."""
import os
import tempfile
import time
import unittest

import invoice_lines as il

TEXT = """Счет на оплату № 1234 от 12 октября 2026 г.
Поставщик: ООО "Галвент", ИНН 7701234567, г. Москва
Покупатель: ООО «КЛИВЭЛ», ИНН 7743151323
 №  Товары (работы, услуги)                          Кол-во  Ед.   Цена        Сумма
 1  Воздуховод круглый оцинк. d125 0,5мм L=1250      10      шт    450,00      4 500,00
 2  Переход 400х150/300х150 оцинк.                    2       шт    1 250,00    2 500,00
 3  Диффузор щелевой 2 щели 1000 мм 15 мм             4       шт    5 200,00    20 800,00
 4  Строка с неверной суммой                          3       шт    100,00      999,00
                                                     Итого:                     27 800,00
                                                     В т.ч. НДС (20%):           4 633,33
"""


class InvoiceRows(unittest.TestCase):
    def test_only_consistent_rows_are_taken(self):
        got = [(r['name'], r['qty'], r['price']) for r in il.rows(TEXT)]
        self.assertEqual([('Воздуховод круглый оцинк. d125 0,5мм L=1250', 10.0, 450.0),
                          ('Переход 400х150/300х150 оцинк', 2.0, 1250.0),
                          ('Диффузор щелевой 2 щели 1000 мм 15 мм', 4.0, 5200.0)], got)

    def test_buyer_inn_does_not_make_it_our_sale(self):
        self.assertFalse(il.seller_is_us(TEXT))
        ours = TEXT.replace('Поставщик: ООО "Галвент", ИНН 7701234567', 'Поставщик: ООО «КЛИВЭЛ», ИНН 7743151323')
        self.assertTrue(il.seller_is_us(ours))


class FreshestIndex(unittest.TestCase):
    def test_the_newer_of_the_two_indexes_is_read(self):
        folder = tempfile.mkdtemp()
        old, new = os.path.join(folder, 'old.json'), os.path.join(folder, 'new.json')
        for path in (old, new):
            with open(path, 'w') as f:
                f.write('[]')
        os.utime(old, (time.time() - 86400 * 50,) * 2)
        saved = il.INDEX_CANDIDATES
        try:
            il.INDEX_CANDIDATES = (old, new)
            self.assertEqual(new, il.newest_index())
        finally:
            il.INDEX_CANDIDATES = saved


if __name__ == '__main__':
    unittest.main()
