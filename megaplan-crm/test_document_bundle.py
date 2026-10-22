import unittest
from document_bundle import validate_invoice

class BundleTests(unittest.TestCase):
    def setUp(self):
        self.invoice={'deal':{'id':'1'},'payer':{'id':'2'},'recipient':{'id':'3'},'sum':{'value':100,'currency':'RUB'}}
    def test_current_parties_required(self):
        validate_invoice(self.invoice,'1','2','3')
        for field in ('deal','payer','recipient'):
            with self.assertRaises(ValueError):validate_invoice({**self.invoice,field:{'id':'other'}},'1','2','3')
    def test_currency_and_nonfinite_fail_closed(self):
        for amount in ({'value':100,'currency':'EUR'},{'value':'NaN','currency':'RUB'}):
            with self.assertRaises(ValueError):validate_invoice({**self.invoice,'sum':amount},'1','2','3')
