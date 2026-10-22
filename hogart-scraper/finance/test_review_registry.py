import json
import tempfile
import unittest
from pathlib import Path
from review_registry import sync, active, owner_context, resolve_manual

class ReviewRegistryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        p=self.root/'evidence/finish_all';p.mkdir(parents=True)
        (p/'owner_questions.json').write_text(json.dumps({'groups':[], 'resolved_groups':[
            {'number':1,'invoices':'42','bank_ids':['old'],'answer':'Примавера'},
            {'number':2,'invoices':'ПКБ-00002943','bank_ids':['old2'],'answer':'Да целиком'}]}))
        self.row=dict(id='new50',status='Требует уточнения',company='КЛИВЭЛ',counterparty='Пономарев',
                      inn='123',category='Оборудование',amount_cents=3500000,flags=['Нужен счёт 50'],
                      document_numbers='50',purpose='Оплата по счету №50')
    def tearDown(self):self.tmp.cleanup()
    def test_rebuild_is_idempotent_and_old_answer_does_not_close_new_invoice(self):
        one=sync([self.row],self.root,{})
        two=sync([self.row],self.root,{})
        self.assertEqual(list(one['tasks']),list(two['tasks']))
        self.assertEqual(len(active(two)),1)
        self.assertEqual(two['historical_answers'][1]['answer'],'Да целиком')
        self.assertEqual(owner_context(self.root)['groups'][0]['invoices'],'50')
        self.assertTrue(owner_context(self.root)['resolved_groups'][0]['resolved'])
    def test_resolved_movement_closes_task_but_keeps_history(self):
        sync([self.row],self.root,{})
        self.row['status']='Проведено в Мегаплане'
        reg=sync([self.row],self.root,{})
        self.assertEqual(active(reg),[])
        self.assertEqual(reg['tasks']['bank:new50']['state'],'resolved')
    def test_document_followup_is_not_closed_by_payment_posting(self):
        path=self.root/'evidence/deep_review';path.mkdir()
        (path/'non_owner_followup.json').write_text(json.dumps([
            {'old_question':70,'bank_ids':['new50'],'task':'Нужен обновлённый документ'}]))
        self.row['status']='Проведено в Мегаплане'
        reg=sync([self.row],self.root,{})
        key=active(reg)[0]['id']
        self.assertEqual(len(active(sync([self.row],self.root,{}))),1)
        with self.assertRaises(ValueError):resolve_manual(key,'',self.root)
        resolve_manual(key,'Сверено с документом /archive/invoice.pdf',self.root)
        self.assertEqual(active(sync([self.row],self.root,{})),[])

    def test_stock_consumption_not_counted_as_missing_allocation(self):
        data={'invoices':[dict(document_key='i',number='N',supplier='S',total=100,allocations=[{'amount':60}])],
              'unallocated_stock':[dict(id='s',document_key='i',available_amount=10,available_qty=1,
                                       name='Cable',allocations=[{'amount':30}])]}
        reg=sync([],self.root,data)
        self.assertEqual([(x['id'],x['amount_cents']) for x in active(reg)],[('stock:s',1000)])
    def test_confirmed_purpose_with_unfinished_paperwork_remains_work(self):
        self.row['status']='Назначение подтверждено; оформление отдельно'
        reg=sync([self.row],self.root,{})
        self.assertEqual(active(reg)[0]['kind'],'bank_followup')
        self.assertEqual(active(reg)[0]['owner'],'assistant')

if __name__=='__main__':unittest.main()
