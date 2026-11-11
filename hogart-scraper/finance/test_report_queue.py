"""11.11: a queue task without «supplier» failed report.py — no Excel, no owner questions."""
import unittest

from report import queue_row


class QueueRowTests(unittest.TestCase):
    def test_task_of_another_module_without_bank_fields_is_reported(self):
        row = queue_row({'id': 'spec:1', 'kind': 'spec_refresh', 'owner': 'assistant', 'state': 'open',
                         'action': 'Обновить спецификацию'})
        self.assertEqual('spec:1', row[0]); self.assertEqual('', row[2]); self.assertEqual(0, row[5])
        self.assertEqual(0, row[6]); self.assertEqual('Ассистент', row[8])

    def test_owner_question_keeps_all_fields(self):
        row = queue_row({'id': 'bank:a', 'company': 'КЛИВЭЛ', 'supplier': 'АО "Альфа-Банк"', 'inn': '7728168971',
                         'category': 'Покупки по корпоративной карте', 'bank_ids': ['a'], 'amount_cents': 41300,
                         'action': 'покупка по карте…', 'owner': 'user'})
        self.assertEqual(['bank:a', 'КЛИВЭЛ', 'АО "Альфа-Банк"'], row[:3])
        self.assertEqual(413.0, row[6]); self.assertEqual('Пользователь', row[8]); self.assertEqual('a', row[9])


if __name__ == '__main__':
    unittest.main()
