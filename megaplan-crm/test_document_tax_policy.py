import unittest
from unittest.mock import Mock
from document_tax_policy import require_no_vat

class TaxPolicyTests(unittest.TestCase):
    def test_known_no_vat_requires_no_network(self):
        api=Mock(); require_no_vat({'positions':[{'tax':{'rate':-1}}]},api); api._call.assert_not_called()
    def test_reference_is_resolved_once(self):
        api=Mock(); api._call.return_value={'data':[{'id':'7','rate':-1}]}
        require_no_vat({'positions':[{'tax':{'id':'7'}},{'tax':{'id':'7'}}]},api)
        api._call.assert_called_once_with('GET','/tax')
    def test_taxable_zero_and_unknown_are_not_exempt(self):
        for rate in (0,5,22,None):
            with self.assertRaises(ValueError): require_no_vat({'positions':[{'tax':{'rate':rate}}]},Mock())
    def test_empty_specification_is_rejected(self):
        with self.assertRaises(ValueError): require_no_vat({},Mock())

if __name__=='__main__': unittest.main()
