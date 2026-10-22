import unittest,io,zipfile
from mail_intake import inspect_archive
from test_ledger import LedgerTests
class MailIntakeTests(unittest.TestCase):
 def pack(self,name,content):
  b=io.BytesIO()
  with zipfile.ZipFile(b,'w') as z:z.writestr(name,content)
  return b.getvalue()
 def test_payment_pdf_is_not_a_statement(self):
  self.assertFalse(inspect_archive(self.pack('payment.pdf',b'%PDF'),{}))
 def test_known_account_validated(self):
  raw=LedgerTests().statement();self.assertTrue(inspect_archive(self.pack('statement.txt',raw),{'111':{}}))
 def test_foreign_account_rejected(self):
  with self.assertRaisesRegex(ValueError,'Unknown company account'):inspect_archive(self.pack('statement.txt',LedgerTests().statement()),{'222':{}})
 def test_bad_balance_rejected(self):
  raw=LedgerTests().statement().replace(b'900.0',b'800.0')
  with self.assertRaises(ValueError):inspect_archive(self.pack('statement.txt',raw),{'111':{}})

class MailReconnectTests(unittest.TestCase):
 def test_transient_disconnect_retries(self):
  import imaplib
  from unittest.mock import patch
  from mail_intake import retrieve
  with patch('mail_intake._retrieve_once',side_effect=[imaplib.IMAP4.abort('disconnected'),[]]) as call,patch('time.sleep'):
   self.assertEqual(retrieve(),[]);self.assertEqual(call.call_count,2)
 def test_authentication_error_is_not_retried(self):
  import imaplib
  from unittest.mock import patch
  from mail_intake import retrieve
  with patch('mail_intake._retrieve_once',side_effect=imaplib.IMAP4.error('authentication failed')) as call:
   with self.assertRaises(imaplib.IMAP4.error):retrieve()
   self.assertEqual(call.call_count,1)
