"""28.11: «Общий итог:331.300» was read as a work — the installer's report total came out almost ×2."""
import unittest

import installer_report_text as t


class GrandTotalIsNotAWork(unittest.TestCase):
    def test_grand_total_and_wrapped_lines(self):
        rows = t.parse_rows('''Сделка №905
Монтаж теплого пола по таблице-31.000
Итого:31.000
Отверстия и штробы под зелёные
стены-10.000
Итого:10.000
Общий итог:41.000''')
        works = [r for r in rows if r[7] == 1]
        self.assertEqual([31000.0, 10000.0], [r[6] for r in works])
        self.assertEqual('Отверстия и штробы под зелёные стены-10.000', works[1][1])
        self.assertEqual(0, rows[-1][7])
        self.assertEqual('Контроль отчёта', rows[-1][0])


if __name__ == '__main__':
    unittest.main()
