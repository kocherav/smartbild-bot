import unittest
from unittest.mock import patch
from crm_context import enrich

class ContextTests(unittest.TestCase):
    def row(self):
        return {'company':'ИНСИС','account':'111','date':'2026-09-25','number':'140','direction':'out','amount_cents':10000,'inn':'supplier','purpose':'Оплата по счету №12','project':'','flags':['Нет подтверждённой привязки к объекту/заказу'],'status':'Требует уточнения'}
    def source(self,name,default):
        return {'procurement_registry.json':{'invoices':[{'id':'a','number':'12','supplier_inn':'supplier','buyer_inn':'buyer','total':100,'allocations':[{'deal_id':'887','amount':100}]}]},'deal_browser_cache.json':[{'id':'887','name':'Example'}]}.get(name,default)
    def test_exact_invoice(self):
        with patch('crm_context.read',side_effect=self.source):
            r=enrich([self.row()],{'111':{'inn':'buyer'}})[0]
            self.assertIn('887',r['project']);self.assertEqual(r['crm_operations'],'')
    def test_wrong_buyer_is_not_linked(self):
        with patch('crm_context.read',side_effect=self.source):
            r=enrich([self.row()],{'111':{'inn':'different'}})[0]
            self.assertEqual(r['project'],'');self.assertEqual(r['status'],'Требует уточнения')
    def test_partial_payment_not_auto_linked(self):
        row=self.row();row['amount_cents']=9000
        with patch('crm_context.read',side_effect=self.source):
            r=enrich([row],{'111':{'inn':'buyer'}})[0]
            self.assertEqual(r['project'],'');self.assertEqual(r['crm_candidate'],'887')
if __name__=='__main__':unittest.main()
