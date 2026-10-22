import unittest
from datetime import date
from unittest.mock import patch,Mock
import contract_invoice as ci

from contract_invoice import basis_from_deal, build_invoice_v1_forms, contract_basis, parse_contract, full_invoice_rows


TEXT = """
ДОГОВОР № 1.888-1709/2026
от 17.09.2026
6.4.1 Заказчик перечисляет на расчётный счёт Поставщика предоплату в размере 1 367 930,00 (один миллион) рублей.
6.4.2 Окончательный расчёт в размере 579 608,00 (пятьсот тысяч) рублей.
6.5. Иные условия.
"""


class ContractInvoiceTests(unittest.TestCase):
    def test_docx_payment_clauses_separated_by_soft_breaks(self):
        import tempfile
        from pathlib import Path
        from docx import Document
        from docx.oxml import OxmlElement
        with tempfile.TemporaryDirectory() as directory:
            doc=Document();doc.add_paragraph('ДОГОВОР № TEST от 17.09.2026')
            run=doc.add_paragraph().add_run('6.4.1 Предоплата в размере 400 000 рублей.')
            run.add_break();run.add_text('6.4.2');run.add_tab()
            run.add_text('Предоплата что составляет 967\xa0930 рублей.')
            run._r.append(OxmlElement('w:cr'))
            run.add_text('6.4.3 Окончательный расчет в размере 579 608 рублей.')
            doc.add_paragraph('6.5. Иные условия.')
            path=Path(directory)/'contract.docx';doc.save(path)
            text=ci.document_text(path)
            for clause,amount in [('6.4.1',400000),('6.4.2',967930),('6.4.3',579608)]:
                self.assertEqual(ci.parse_contract(text,clause)['amount'],amount)
            self.assertIn('6.4.2\tПредоплата',text)

    def test_registration_date_is_not_contract_date(self):
        text=TEXT.replace('от 17.09.2026','г. Москва 17.09.2026\nИндивидуальный предприниматель Example, ОГРНИП от 08.11.2024')
        self.assertEqual('17.09.2026',parse_contract(text,'6.4.1')['contract_date'])
        missing=TEXT.replace('от 17.09.2026','Индивидуальный предприниматель Example, ОГРНИП от 08.11.2024')
        with self.assertRaisesRegex(ValueError,'дату'):parse_contract(missing,'6.4.1')
        inline=TEXT.replace('1.888-1709/2026\nот','1.888-1709/2026 от')
        self.assertEqual('1.888-1709/2026',parse_contract(inline,'6.4.1')['contract_number'])
    def test_document_text_includes_nested_party_requisites(self):
        import tempfile
        from pathlib import Path
        from docx import Document
        with tempfile.TemporaryDirectory() as directory:
            document=Document();document.add_paragraph('ДОГОВОР № 1')
            outer=document.add_table(rows=1,cols=2)
            nested=outer.cell(0,1).add_table(rows=1,cols=1)
            nested.cell(0,0).text='ИНН 2222222222'
            path=Path(directory)/'contract.docx';document.save(path)
            self.assertIn('ИНН 2222222222',ci.document_text(path))
    def test_contract_must_match_current_parties_number_and_date(self):
        seller={'inn':'1111111111'};payer={'inn':'2222222222'}
        text=TEXT+'\nИНН 1111111111\nИНН 2222222222'
        parsed=parse_contract(text,'6.4.1')
        deal={'Category1000068CustomFieldNomerDogovora':'1.888-1709/2026',
              'Category1000068CustomFieldDataDogovora':{'day':17,'month':8,'year':2026}}
        ci.validate_contract_context(text,parsed,deal,seller,payer)
        for changed in ({**deal,'Category1000068CustomFieldNomerDogovora':'another'},
                        {**deal,'Category1000068CustomFieldDataDogovora':{'day':18,'month':8,'year':2026}}):
            with self.assertRaisesRegex(ValueError,'не совпадают'):
                ci.validate_contract_context(text,parsed,changed,seller,payer)
        with self.assertRaisesRegex(ValueError,'ИНН'):
            ci.validate_contract_context(text,parsed,deal,{'inn':'333333333333'},payer)
        with self.assertRaisesRegex(ValueError,'ИНН'):
            ci.validate_contract_context(text,parsed,deal,seller,{'inn':'4444444444'})

    def test_contract_inn_cannot_match_inside_another_number(self):
        parsed=parse_contract(TEXT,'6.4.1')
        with self.assertRaisesRegex(ValueError,'ИНН'):
            ci.validate_contract_context(TEXT+' 911111111119',parsed,{}, {'inn':'1111111111'},{'inn':'2222222222'})
    def test_changed_preview_never_creates_invoice(self):
        for fn,preview_name in ((ci.create,'preview'),(ci.create_full,'preview_full')):
            with patch.object(ci,preview_name,return_value={'fingerprint':'new'}), patch.object(ci,'create_v1_invoice') as write:
                result=fn({'expected_fingerprint':'old'},Mock())
            self.assertTrue(result['no_effect']); write.assert_not_called()

    def test_preview_identity_includes_seller_payer_and_amount(self):
        base={'deal_id':'1','payer_id':'2','recipient_id':'3','rows':[{'price':'10','quantity':'1'}]}
        key=ci.preview_fingerprint(base)
        for field,value in [('payer_id','4'),('recipient_id','5'),('rows',[{'price':'20','quantity':'1'}])]:
            self.assertNotEqual(key,ci.preview_fingerprint({**base,field:value}))

    def test_full_invoice_uses_net_discounted_price_once(self):
        rows = full_invoice_rows({'price': {'value': 1500, 'currency': 'RUB'}, 'positions': [
            {'offer': {'id': '7', 'name': 'Example'}, 'quantity': 2,
             'price': {'value': 1000}, 'discount': {'value': 25}, 'sum': {'value': 1500, 'currency': 'RUB'}}]})
        self.assertEqual('750', rows[0]['price'])

    def test_full_invoice_mismatch_rejected_before_write(self):
        with self.assertRaises(ValueError):
            full_invoice_rows({'price': {'value': 123}, 'positions': [
                {'offer': {'id': '7'}, 'quantity': 2, 'sum': {'value': 1500}}]})

    def test_advance_line_comes_from_clause(self):
        result = parse_contract(TEXT, "6.4.1")
        self.assertEqual(result["amount"], 1367930)
        self.assertEqual(
            result["line"],
            "Авансовый платеж, согласно п.6.4.1 Договора № 1.888-1709/2026 от 17.09.2026, сумма 1 367 930,00 руб.",
        )

    def test_second_payment_uses_its_own_amount(self):
        result = parse_contract(TEXT, "6.4.2")
        self.assertEqual(result["amount"], 579608)
        self.assertTrue(result["line"].startswith("Окончательный платеж, согласно п.6.4.2"))

    def test_amount_written_as_rubles_and_kopecks(self):
        text = TEXT.replace(
            "предоплату в размере 1 367 930,00 (один миллион) рублей",
            "предоплату в размере 100% от стоимости, что составляет 400 000 рублей 00 копеек (четыреста тысяч рублей)",
        )
        result = parse_contract(text, "6.4.1")
        self.assertEqual(result["amount"], 400000)
        self.assertIn("сумма 400 000,00 руб.", result["line"])

    def test_missing_clause_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "6.4.3"):
            parse_contract(TEXT, "6.4.3")

    def test_invoice_contains_exactly_one_custom_row_and_deal_link(self):
        parsed = parse_contract(TEXT, "6.4.1")
        parsed.update({"deal_id": "888", "payer_id": "1003408"})
        draft, row, issue = build_invoice_v1_forms(parsed, "42", date(2026, 9, 17))
        self.assertEqual(draft["Deal"], "888")
        self.assertEqual(draft["Model[Payer]"], "1003408")
        self.assertEqual(draft["Model[InvoiceTemplate]"], "3")
        self.assertEqual(draft["Model[Status]"], 1)
        self.assertEqual(issue["Model[Status]"], 2)
        self.assertEqual(row["Model[Name]"], parsed["line"])
        self.assertEqual(row["Model[Price]"], 1367930)
        self.assertEqual(draft["Model[PaymentOrderNumber]"], "Договор № 1.888-1709/2026 от 17.09.2026")
        self.assertEqual(issue["Model[PaymentOrderNumber]"], "Договор № 1.888-1709/2026 от 17.09.2026")

    def test_full_invoice_basis_comes_from_deal_contract_fields(self):
        deal = {
            "number": "894",
            "Category1000068CustomFieldNomerDogovora": "1.894-2109/2026",
            "Category1000068CustomFieldDataDogovora": {"year": 2026, "month": 8, "day": 22},
        }
        self.assertEqual(basis_from_deal(deal), "Договор № 1.894-2109/2026 от 22.09.2026")

    def test_invoice_without_contract_reference_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "номер или дата договора"):
            contract_basis("", "22.09.2026")


if __name__ == "__main__":
    unittest.main()
