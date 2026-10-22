import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
import hogart_closing as h


class HogartClosingTests(unittest.TestCase):
    def setUp(self):
        self.invoice = dict(id='i', number='79566', date='22.09.2026', total=167011.20,
                            buyer_inn='7743926877', supplier_inn='7717632694')
        self.bill = dict(id=1, number='79566', docDate='2026-09-22', orderId=224331,
                         type={'id': 1}, legalEntity={'inn': '7743926877'}, documentItemsTotalPrice=167011.20)
        self.upd = dict(self.bill, id=2, number='TR0000031349', type={'id': 2})
        self.docs = [self.bill, self.upd]
        self.text = ('ИНН/КПП продавца: 7717632694/771701001 ИНН/КПП покупателя: 7743926877/771401001 '
                     'Счет-фактура № TR0000031349 от 30 сентября 2026 г. '
                     'Всего к оплате (9) 136 894,43 Х 30 116,77 167 011,20 Документ '
                     'Основание передачи Счет № 79566 от 22 сентября 2026')

    def test_fresh_pagination_collects_all_pages(self):
        api = Mock(); api._call.side_effect = [dict(items=[self.bill], meta=dict(currentPage=1, pageCount=2, totalCount=2)), dict(items=[self.upd], meta=dict(currentPage=2, pageCount=2, totalCount=2))]
        self.assertEqual(h.documents(api), self.docs)
        self.assertEqual(api._call.call_args.kwargs['params'], {'page': 2})

    def test_repeated_page_rejected(self):
        api = Mock(); api._call.side_effect = [dict(items=[self.bill], meta=dict(currentPage=1, pageCount=2, totalCount=3)), dict(items=[self.bill], meta=dict(currentPage=2, pageCount=2, totalCount=3))]
        with self.assertRaises(ValueError): h.documents(api)

    def test_live_api_count_mismatch_preserves_warning_and_positive_evidence(self):
        api = Mock(); api._call.side_effect = [dict(items=[self.bill], meta=dict(currentPage=1, pageCount=2, totalCount=3)), dict(items=[self.upd], meta=dict(currentPage=2, pageCount=2, totalCount=3))]
        docs = h.documents(api)
        self.assertIn('отсутствие других документов', docs.warning)
        self.assertEqual(h.candidates(self.invoice, docs)['id'], 2)

    def test_match_requires_order_buyer_date_and_full_total(self):
        self.assertEqual(h.candidates(self.invoice, self.docs)['id'], 2)
        for key, value in [('orderId', 999), ('documentItemsTotalPrice', 10), ('legalEntity', {'inn': 'wrong'})]:
            docs = copy.deepcopy(self.docs); docs[1][key] = value
            with self.assertRaises(ValueError): h.candidates(self.invoice, docs)
        invoice = dict(self.invoice, date='23.09.2026')
        with self.assertRaises(ValueError): h.candidates(invoice, self.docs)

    def test_ambiguous_partial_and_duplicate_documents_require_review(self):
        for docs in [self.docs + [self.upd], self.docs + [self.bill], [self.bill]]:
            with self.assertRaises(ValueError): h.candidates(self.invoice, docs)

    def test_pdf_identity_and_total_not_just_equal_metadata(self):
        h.validate_text(self.text, self.invoice, self.upd)
        for old, new in [('79566', '79567'), ('22 сентября', '23 сентября'), ('7717632694', '7743926877'), ('167 011,20', '167 011,19'), ('TR0000031349', 'TR0000031350')]:
            with self.assertRaises(ValueError): h.validate_text(self.text.replace(old, new), self.invoice, self.upd)

    def test_external_download_host_rejected(self):
        with self.assertRaises(ValueError): h.fetch(dict(self.upd, fileUrl='https://example.test/file'), self.invoice, '.')

    def run_sync(self, publish=True, archive_error=False):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        path = Path(tmp.name)/'upd.pdf'; path.write_bytes(b'%PDF-test')
        crm = Mock(); crm.upload_file.return_value = {'id': 'file'}; crm._call.return_value = {'data': {'id': 'comment'}}
        receipt = {}; calls = []
        def effect(key, action):
            calls.append(key)
            if key not in receipt: receipt[key] = action()
            return receipt[key]
        with patch('hogart_api.HogartAPI'), patch.object(h, 'documents', return_value=self.docs), patch.object(h, 'fetch', return_value=(path, 'sha')), patch('procurement_workflow.supplier_invoices_for_deal', return_value=[self.invoice]), patch('procurement_workflow.record_closing_document') as record, patch('financial_archive.archive_document', side_effect=TimeoutError if archive_error else None, return_value={'ok': True}) as archive:
            messages = h.sync('887', tmp.name, crm, effect, publish)
            if publish and not archive_error:
                h.sync('887', tmp.name, crm, effect, publish)
                self.assertEqual(crm.upload_file.call_count, 1)
                self.assertEqual(crm._call.call_count, 1)
                self.assertEqual(archive.call_count, 1)
            return messages, record.call_count, crm, calls

    def test_live_routes_original_without_financial_writes(self):
        messages, registered, crm, calls = self.run_sync()
        self.assertIn('сохранён в OneDrive', messages[0]); self.assertEqual(registered, 2)
        self.assertTrue(all(c.args[1] == '/deal/887/comments' for c in crm._call.call_args_list))
        self.assertTrue(any(k.endswith('-upload') for k in calls))

    def test_archive_failure_never_records_closing_received(self):
        messages, registered, crm, calls = self.run_sync(archive_error=True)
        self.assertEqual(registered, 0); self.assertIn('OneDrive не завершены', messages[0])

    def test_test_mode_has_no_external_writes(self):
        messages, registered, crm, calls = self.run_sync(publish=False)
        self.assertEqual(registered, 0); self.assertEqual(calls, []); crm.upload_file.assert_not_called()

    def test_already_registered_skips_account_query(self):
        with patch('procurement_workflow.supplier_invoices_for_deal', return_value=[dict(self.invoice, closing_documents=[{'sha256': 'sha'}])]), patch('hogart_api.HogartAPI') as api:
            self.assertEqual(h.sync('887', '.', Mock(), Mock()), []); api.assert_not_called()

    def test_unavailable_account_is_reported_not_absence(self):
        with patch('procurement_workflow.supplier_invoices_for_deal', return_value=[self.invoice]), patch('hogart_api.HogartAPI', side_effect=TimeoutError):
            result = h.sync('887', '.', Mock(), Mock())
            self.assertIn('недоступна', result[0])
