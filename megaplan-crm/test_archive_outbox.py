from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import archive_outbox as outbox


class OutboxTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup); self.root=Path(tmp.name)
        p=patch.object(outbox,'ROOT',self.root/'spool'); p.start(); self.addCleanup(p.stop)
        self.file=self.root/'Счёт.pdf'; self.file.write_bytes(b'anonymous invoice')
        self.spec={'deal_id':'demo','category':'supplier_invoice','path':str(self.file)}

    def test_original_survives_temporary_file_removal_and_delivery_is_deduplicated(self):
        queued=outbox.enqueue(self.spec); self.assertTrue(queued['queued'])
        self.assertEqual(queued['archive_job_id'],outbox.enqueue(self.spec)['archive_job_id'])
        self.file.unlink()
        def archive(**payload):
            self.assertEqual(b'anonymous invoice',Path(payload['path']).read_bytes())
            self.assertEqual('Счёт.pdf',payload['display_name'])
            return {'ok':True,'onedrive_remote':'fake:archive'}
        with patch('financial_archive.archive_document',side_effect=archive) as uploader:
            self.assertEqual('done',outbox.drain()['jobs'][0]['status'])
            self.assertEqual([],outbox.drain()['jobs']); uploader.assert_called_once()

    def test_failure_keeps_document_and_backs_off(self):
        outbox.enqueue(self.spec)
        with patch('financial_archive.archive_document',side_effect=TimeoutError()) as uploader:
            self.assertEqual('pending',outbox.drain()['jobs'][0]['status'])
            self.assertEqual([],outbox.drain()['jobs']); uploader.assert_called_once()
        db=outbox.connect(); db.execute('UPDATE jobs SET updated=0'); db.commit(); db.close()
        with patch('financial_archive.archive_document',return_value={'ok':True}):
            self.assertEqual('done',outbox.drain()['jobs'][0]['status'])


if __name__=='__main__': unittest.main()
