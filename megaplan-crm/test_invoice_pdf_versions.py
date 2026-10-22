import hashlib,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import invoice_pdf_versions as p
class PDFVersionsTest(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
  mock=patch.object(p,'ROOT',self.root);mock.start();self.addCleanup(mock.stop)
  self.invoice={'id':'836','number':'10499','sum':{'value':152200,'currency':'RUB'},'rows':[]}
 def install(self):
  (self.root/'corrected.pdf').write_bytes(b'%PDF-approved')
  (self.root/'836.json').write_text(json.dumps({'filename':'corrected.pdf','invoice_fingerprint':p.fingerprint(self.invoice),'sha256':hashlib.sha256(b'%PDF-approved').hexdigest()}))
 def test_no_correction_returns_default(self):self.assertIsNone(p.approved_pdf(self.invoice))
 def test_approved_file_used_and_paid_status_does_not_invalidate(self):
  self.install();self.invoice['status']='paid';result=Path(p.approved_pdf(self.invoice));self.assertEqual(b'%PDF-approved',result.read_bytes());result.unlink();self.assertTrue((self.root/'corrected.pdf').exists())
 def test_changed_money_or_file_is_rejected(self):
  self.install();self.invoice['sum']['value']=1
  with self.assertRaises(ValueError):p.approved_pdf(self.invoice)
  self.invoice['sum']['value']=152200;(self.root/'corrected.pdf').write_bytes(b'changed')
  with self.assertRaises(ValueError):p.approved_pdf(self.invoice)
if __name__=='__main__':unittest.main()
