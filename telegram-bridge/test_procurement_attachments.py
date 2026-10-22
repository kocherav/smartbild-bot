import hashlib,json,tempfile,unittest,zipfile
from pathlib import Path
from unittest.mock import Mock
import procurement_attachments as a

class AttachmentTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name);self.reg=self.root/'archive.json'
  self.raw=b'%PDF-supplier';self.sha=hashlib.sha256(self.raw).hexdigest()
  self.entry=dict(deal_id='887',category='supplier_invoice',status='uploaded',filename='Счёт.pdf',sha256=self.sha,document_number='79566',onedrive_remote='source')
  self.invoice=dict(number='79566',total=100,paid_total=100,buyer='Инсис',supplier='Трио Климат')
 def build(self,entries=None,downloader=None):
  self.reg.write_text(json.dumps({'documents':entries if entries is not None else [self.entry]}))
  return a.build('887',self.root/'out',self.reg,[self.invoice],downloader=downloader or (lambda remote,path:path.write_bytes(self.raw)))
 def test_verified_file_and_register_in_zip_without_links(self):
  result=self.build()
  with zipfile.ZipFile(result['attachments'][0]) as z:
   self.assertEqual(len(z.namelist()),2);self.assertEqual(z.read(result['files'][0]['name']),self.raw)
   text=z.read('00 — Реестр документов.txt').decode();self.assertIn('79566',text);self.assertIn('оплачено 100',text);self.assertNotIn('https://',text)
 def test_wrong_digest_blocks_delivery(self):
  with self.assertRaisesRegex(ValueError,'контрольная сумма'):self.build(downloader=lambda r,p:p.write_bytes(b'bad'))
 def test_other_deal_pending_and_duplicate_not_included(self):
  result=self.build([self.entry,self.entry,dict(self.entry,deal_id='890'),dict(self.entry,status='pending')]);self.assertEqual(len(result['files']),1)
 def test_missing_original_explicit(self):
  result=self.build([]);self.assertIn('ФАЙЛ НЕ ВКЛЮЧЁН',result['register'])
 def test_cached_original_verified_no_redownload(self):
  self.build();download=Mock(side_effect=AssertionError('Already cached'));self.build(downloader=download);download.assert_not_called()
 def test_paths_cannot_escape_zip(self):
  result=self.build([dict(self.entry,filename='../../evil.pdf')]);self.assertNotIn('/',result['files'][0]['name']);self.assertEqual(Path(result['files'][0]['path']).parent,self.root/'out')
 def test_email_has_pdf_and_zip_mime(self):
  pdf=self.root/'act.pdf';pdf.write_bytes(b'%PDF');result=self.build();messages=a.email_messages('from@example.test','to@example.test','ТЕСТ','body',[pdf,*result['attachments']],'test')
  parts=list(messages[0].iter_attachments());self.assertEqual([p.get_content_type() for p in parts],['application/pdf','application/zip'])
  self.assertEqual(parts[1].get_payload(decode=True),Path(result['attachments'][0]).read_bytes())
 def test_email_split_uses_actual_encoded_size_and_unique_ids(self):
  paths=[]
  for i in range(3):p=self.root/f'{i}.pdf';p.write_bytes(bytes(range(256))*6);paths.append(p)
  messages=a.email_messages('a@example.test','b@example.test','ТЕСТ','body',paths,'test',limit=4000)
  self.assertEqual(len(messages),3);self.assertEqual(len({m['Message-ID'] for m in messages}),3)
  self.assertTrue(all(len(m.as_bytes())<=4000 for m in messages))
 def test_oversized_single_file_reported_not_omitted(self):
  p=self.root/'large.pdf';p.write_bytes(b'x'*5000)
  with self.assertRaisesRegex(ValueError,'превышает'):a.email_messages('a@b.test','c@d.test','test','body',[p],'test',limit=3000)
