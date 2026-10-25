import tempfile
import unittest
from pathlib import Path

import requisites_card


class RequisitesCardTests(unittest.TestCase):
    def test_word_conversion_with_identifiers_in_one_heading(self):
        # Layout of the Barion card after the office Word->Markdown conversion
        # (05.05.26): ИНН/КПП/ОГРН share one heading line and must not be glued
        # together; bank rows are a bold Markdown table.  Rebuilt here so the
        # regression runs without the client's file from the server inbox.
        text = """**КАРТОЧКА ОРГАНИЗАЦИИ**
**ООО «Барион»**
**ИНН 2465183456 КПП 772401001 ОГРН 1182468000000**

| **Полное наименование организации** | **Общество с ограниченной ответственностью «Барион»** |
| **Юридический адрес** | **г. Москва** |
| **Расчетный счет** | **40702810634100032989** |
| **Корреспондентский счет** | **30101810145250000201** |
| **БИК** | **044525201** |
| **Наименование банка** | **Тест Банк** |
| **Генеральный директор** | **Медведко Артем Сергеевич** |
"""
        card = requisites_card.parse_document_from_text(text)
        self.assertEqual(card["inn"], "2465183456")
        self.assertEqual(card["kpp"], "772401001")
        self.assertEqual(card["ogrn"], "1182468000000")
        self.assertEqual(card["currentAccount"], "40702810634100032989")
        self.assertEqual(card["bik"], "044525201")
        self.assertEqual(card["director"], "Медведко Артем Сергеевич")

    def test_markdown_file_is_read_from_disk(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "card.docx.md"
            path.write_text("КАРТОЧКА ОРГАНИЗАЦИИ\nООО «Тест»\nИНН 9726074760\nКПП 772601001\n"
                            "Расчетный счет 40702810700210000301\nБИК 044525659\n", encoding="utf-8")
            self.assertEqual(requisites_card.parse_document(str(path))["inn"], "9726074760")

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
