import unittest
from pathlib import Path

import requisites_card


class RequisitesCardTests(unittest.TestCase):
    def test_real_barion_word_conversion(self):
        path = Path("/home/kocher.av/hogart-scraper/incoming/1789651901-КАРТОЧКА_БАРИОН_05.05.26_АВАНГАРД.docx.md")
        card = requisites_card.parse_document(str(path))
        self.assertEqual(card["inn"], "2465183456")
        self.assertEqual(card["kpp"], "772401001")
        self.assertEqual(card["currentAccount"], "40702810634100032989")
        self.assertEqual(card["bik"], "044525201")
        self.assertEqual(card["director"], "Медведко Артем Сергеевич")

    def test_does_not_treat_commercial_text_as_card(self):
        text = "Коммерческое предложение\nООО Климат\nИНН 1234567890\nИтого 500 000 руб."
        self.assertFalse(requisites_card.is_requisites_card(text))

    def test_markdown_table_with_bold_labels(self):
        text = '''**УЧЕТНАЯ КАРТОЧКА ОРГАНИЗАЦИИ**
| **Полное наименование организации** | **ООО "Тест"** |
| **ИНН** | **9726074760** |
| **КПП** | **772601001** |
| **Расчетный счет** | **40702810700210000301** |
| **Корреспондентский счет** | **30101810745250000659** |
| **БИК** | **044525659** |
| **Наименование банка** | **Тест Банк** |'''
        card = requisites_card.parse_document_from_text(text)
        self.assertEqual(card["name"], 'ООО "Тест"')
        self.assertEqual(card["inn"], "9726074760")
        self.assertEqual(card["currentAccount"], "40702810700210000301")

    def test_does_not_concatenate_identifiers_on_one_heading_line(self):
        text = '''УЧЕТНАЯ КАРТОЧКА ОРГАНИЗАЦИИ
ООО "Тест"
ИНН 9726074760 КПП 772601001 ОГРН 1247700347707
Расчетный счет 40702810700210000301
Корреспондентский счет 30101810745250000659
БИК 044525659'''
        card = requisites_card.parse_document_from_text(text)
        self.assertEqual(card["inn"], "9726074760")
        self.assertEqual(card["kpp"], "772601001")
        self.assertEqual(card["ogrn"], "1247700347707")


if __name__ == "__main__":
    unittest.main()
