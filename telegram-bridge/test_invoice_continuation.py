import tempfile,time,unittest
from pathlib import Path
import invoice_continuation as c
class InvoiceContinuationTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.path=Path(self.tmp.name)/'invoice.xlsx';self.path.write_bytes(b'original')
  self.attachment=c.remember(self.path,'Счет-оферта на оплату № 1624 от 22 июня 2026 г.\nИНН 7743949955\nИНН 7743926877',123)
  self.spec={'deal_id':'807','invoice':{'number':'1624','supplier_inn':'7743949955','buyer_inn':'7743926877','source_path':'/invented'}}
 def test_followup_uses_original_attachment_not_model_path(self):
  result=c.bind(self.spec,self.attachment,123)
  self.assertEqual(result['invoice']['source_path'],str(self.path))
  self.assertEqual(self.spec['invoice']['source_path'],'/invented')
 def test_wrong_chat_expiry_and_changed_file_block_stale_draft(self):
  self.assertIsNone(c.bind(self.spec,self.attachment,124))
  self.assertIsNone(c.bind(self.spec,self.attachment,123,now=time.time()+86500))
  self.path.write_bytes(b'changed');self.assertIsNone(c.bind(self.spec,self.attachment,123))
 def test_other_invoice_or_company_cannot_reuse_attachment(self):
  self.spec['invoice']['number']='1280';self.assertIsNone(c.bind(self.spec,self.attachment,123))
  self.spec['invoice']['number']='1624';self.spec['invoice']['buyer_inn']='7743151323'
  self.assertIsNone(c.bind(self.spec,self.attachment,123))
 def test_non_invoice_attachment_does_not_authorize_draft(self):
  self.attachment['text']='Реквизиты 7743949955 7743926877';self.assertIsNone(c.bind(self.spec,self.attachment,123))
if __name__=='__main__':unittest.main()
