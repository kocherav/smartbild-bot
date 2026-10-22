import os
import tempfile
import unittest
import json
from pathlib import Path
from unittest.mock import Mock, patch
from datetime import datetime,timezone

import financial_archive as archive


class FinancialArchiveTest(unittest.TestCase):
    def test_same_second_same_filename_different_content_gets_distinct_remote(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'invoice.pdf';path.write_bytes(b'first')
            api=Mock();api._call.return_value={'data':{'id':'7','name':'Deal'}}
            with patch.multiple(archive,REGISTRY=str(Path(d)/'registry.json'),LOCK=str(Path(d)/'lock')),patch.object(archive,'datetime') as clock:
                clock.now.return_value=datetime(2026,10,12,tzinfo=timezone.utc)
                first=archive.archive_document('7',str(path),'supplier_invoice',api=api,copier=Mock())
                path.write_bytes(b'second')
                second=archive.archive_document('7',str(path),'supplier_invoice',api=api,copier=Mock())
            self.assertNotEqual(first['onedrive_remote'],second['onedrive_remote'])
    def test_remote_size_mismatch_fails_after_upload(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'invoice.pdf';path.write_bytes(b'abc')
            copy=Mock(returncode=0);stat=Mock(returncode=0,stdout=json.dumps({'Size':2,'IsDir':False}))
            with patch.object(archive.subprocess,'run',side_effect=[copy,stat]) as run:
                with self.assertRaisesRegex(ValueError,'размер'):archive.rclone_copy(str(path),'onedrive:test/invoice.pdf')
            self.assertIn('--immutable',run.call_args_list[0].args[0])
    def test_remote_verification_success(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'invoice.pdf';path.write_bytes(b'abc')
            with patch.object(archive.subprocess,'run',side_effect=[Mock(returncode=0),Mock(returncode=0,stdout=json.dumps({'Size':3,'IsDir':False}))]):
                archive.rclone_copy(str(path),'onedrive:test/invoice.pdf')

    def test_deal_folder_has_required_human_structure(self):
        folder = archive.deal_folder_name({
            "id": "894", "contractor": {"name": "Автосалон JetCar"},
            "Category1000068CustomFieldPredmetDogovora": "Поставка и монтаж системы электроснабжения 6-й этаж НК",
        })
        self.assertEqual("Сделка №894 - Автосалон JetCar - электроснабжение 6-й этаж НК", folder)

    def test_archive_deduplicates_identical_original(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = os.path.join(temporary, "Счёт №1.pdf")
            with open(source, "wb") as target:
                target.write(b"invoice")
            old_registry, old_lock = archive.REGISTRY, archive.LOCK
            archive.REGISTRY, archive.LOCK = os.path.join(temporary, "registry.json"), os.path.join(temporary, "registry.lock")
            calls = []
            try:
                api = type("Api", (), {"_call": lambda self, *args, **kwargs: {"data": {
                    "id": "7", "contractor": {"name": "Клиент"}, "name": "Поставка оборудования"}}})()
                first = archive.archive_document("7", source, "supplier_invoice", "1",
                                                 api=api, copier=lambda src, dst: calls.append(dst))
                second = archive.archive_document("7", source, "supplier_invoice", "1",
                                                  api=api, copier=lambda src, dst: calls.append(dst))
            finally:
                archive.REGISTRY, archive.LOCK = old_registry, old_lock
            self.assertTrue(first["ok"])
            self.assertFalse(first["duplicate"])
            self.assertTrue(second["duplicate"])
            self.assertEqual(1, len(calls))
            self.assertIn("03_Закупки_и_счета_поставщиков", calls[0])

    def test_date_in_human_title_does_not_replace_file_extension(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = os.path.join(temporary, "source.pdf")
            with open(source, "wb") as target:
                target.write(b"invoice")
            old_registry, old_lock = archive.REGISTRY, archive.LOCK
            archive.REGISTRY, archive.LOCK = os.path.join(temporary, "registry.json"), os.path.join(temporary, "registry.lock")
            try:
                api = type("Api", (), {"_call": lambda self, *args, **kwargs: {"data": {
                    "id": "7", "contractor": {"name": "Клиент"}, "name": "Поставка оборудования"}}})()
                result = archive.archive_document("7", source, "supplier_invoice", "1",
                                                  "Счёт №1 от 22.06.2026 — Поставщик",
                                                  api=api, copier=lambda src, dst: None)
            finally:
                archive.REGISTRY, archive.LOCK = old_registry, old_lock
            self.assertTrue(result["filename"].endswith(".pdf"))


if __name__ == "__main__":
    unittest.main()
