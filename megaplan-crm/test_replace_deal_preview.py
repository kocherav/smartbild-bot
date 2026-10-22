import unittest
from unittest.mock import Mock, patch
import replace_deal_from_kp as subject


class PreviewTests(unittest.TestCase):
    def setUp(self):
        self.rows=[{'name':'Example','qty':2,'unit_price':75,'cost_material':30,'cost_work':0,'unit_id':'1'}]
        self.deal={'positions':[{'id':'row1'}],'price':{'value':150}}

    def test_preview_reads_deal_and_returns_frozen_rows(self):
        api=Mock(); api._call.return_value={'data':self.deal}
        with patch.object(subject,'MegaplanAPI',return_value=api), patch.object(subject,'normalize_spec',return_value=self.rows):
            out=subject.run({'deal_id':'1','kp':{},'preview':True})
        self.assertEqual(150,out['total']); self.assertEqual(self.rows,out['rows'])
        api._call.assert_called_once_with('GET','/deal/1'); api.find_or_create_offer.assert_not_called()

    def test_changed_deal_never_overwritten(self):
        api=Mock(); api._call.return_value={'data':self.deal}
        with patch.object(subject,'MegaplanAPI',return_value=api):
            out=subject.run({'deal_id':'1','prepared_rows':self.rows,'expected_fingerprint':'outdated'})
        self.assertTrue(out['no_effect']); api.find_or_create_offer.assert_not_called()

    def test_invalid_number_rejected_before_api(self):
        self.rows[0]['unit_price']=float('nan')
        with patch.object(subject,'MegaplanAPI') as api, self.assertRaises(ValueError):
            subject.run({'deal_id':'1','prepared_rows':self.rows,'preview':True})
        api.assert_not_called()

    def test_commit_uses_confirmed_prices_without_supplier_refresh(self):
        actual={'positions':[{'quantity':2,'price':{'value':75},'offer':{'id':'o'}}]}
        api=Mock(); api._call.side_effect=[{'data':self.deal},{'data':actual},{'data':actual},{'data':actual}]
        api.ledger_from_deal.return_value=[]; api.deal_url.return_value='example'
        with patch.object(subject,'MegaplanAPI',return_value=api), patch.object(subject,'normalize_spec') as lookup, patch.object(subject,'backup_deal'), patch.object(subject.deal_ledger,'save'):
            out=subject.run({'deal_id':'1','prepared_rows':self.rows,'expected_fingerprint':subject.deal_fingerprint(self.deal)})
        self.assertTrue(out['ok']); lookup.assert_not_called()


if __name__=='__main__': unittest.main()
