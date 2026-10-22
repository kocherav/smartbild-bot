import unittest
from shipment_procurement import coverage

class ShipmentProcurementTests(unittest.TestCase):
    def setUp(self):
        self.row={'id':'1','name':'Кабель','quantity':10,'unit':'м','kind':'equipment'}
        self.item={'offer_row_id':'1','name':'Кабель','qty':10,'unit':'м','actual_qty':10,'planned_total':100}
        self.line={'offer_row_id':'1','source_name':'Кабель','qty_used':10}
        self.registry={'deals':{'861':{'items':[self.item]}},'invoices':[{'number':'17','allocations':[{'deal_id':'861','source_lines':[self.line]}]}]}
    def status(self): return coverage('861',[self.row],self.registry)['1']
    def test_full(self): self.assertEqual(self.status()['state'],'full')
    def test_quantity(self):
        for qty in [3,12]:
            self.item['actual_qty']=qty;self.line['qty_used']=qty
            self.assertEqual(self.status()['state'],'attention')
    def test_name(self):
        self.line['source_name']='Кабель другой';self.assertEqual(self.status()['state'],'attention')
        self.assertIn('Кабель другой',self.status()['reason'])
    def test_absent(self):
        self.item['actual_qty']=0;self.registry['invoices']=[]
        self.assertEqual(self.status()['state'],'missing')
    def test_unknown(self): self.assertEqual(coverage('861',[self.row],{})['1']['state'],'attention')
    def test_no_double_count_updates(self):
        self.registry['invoices'][0]['allocations'][0]['updates']=[self.line]
        self.assertEqual(self.status()['state'],'full')
    def test_other_deal_and_unproven_actual(self):
        self.registry['invoices'][0]['allocations'][0]['deal_id']='999'
        self.assertEqual(self.status()['state'],'attention')
    def test_units_and_stale_quantity(self):
        self.item['unit']='шт';self.assertEqual(self.status()['state'],'attention')
        self.item['unit']='м';self.row['quantity']=12;self.assertEqual(self.status()['state'],'attention')
    def test_work(self):
        self.row['kind']='work';self.item['planned_total']=0;self.item['actual_qty']=0;self.registry['invoices']=[]
        self.assertEqual(self.status()['state'],'not_required')
