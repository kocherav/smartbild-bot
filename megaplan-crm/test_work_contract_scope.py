import unittest,tempfile,json,hashlib,copy
from pathlib import Path
from unittest.mock import patch
import work_contract_scope as w
from closing_documents import validate_contract_rows
TEXT='ДОГОВОР ПОДРЯДА № 1.846-0104/2026\n1.2. Подрядчик обязуется произвести работы по проектированию инженерных систем (ЭОМ – внутренние электросети) для помещения.\n1.3. Виды работ определены техническим заданием.\n1.4. Период выполнения работ — 15 рабочих дней, с момента выполнения Заказчиком обязательств по п. 3.2 настоящего договора и передачи дизайнпроекта.\n1.5. Работы считаются выполненными после подписания акта.\n3.1. Цена настоящего Договора составляет 90 000,00 (девяносто тысяч) рублей 00 копеек.\n3.2. Оплата после подписания договора.'
NAME='работы по проектированию инженерных систем (ЭОМ – внутренние электросети)'
class WorkContractTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.data={'deal_id':'7','positions':[{'id':'r','name':'Старое название','kind':'work','quantity':'1','total':'90000','unit':'шт.'}]}
  Path(self.tmp.name,'7-source.json').write_text(json.dumps({'work_scope':{'text_sha256':hashlib.sha256(TEXT.encode()).hexdigest(),'row_id':'r','original_name':'Старое название','document_name':NAME}}))
  p=patch.object(w,'ROOT',Path(self.tmp.name));p.start();self.addCleanup(p.stop)
 def test_real_work_contract_boundary(self):
  result=w.apply(self.data,TEXT);rows=validate_contract_rows(TEXT,result['positions'])
  self.assertEqual(NAME,rows[0]['name']);self.assertEqual('90000',rows[0]['total']);self.assertIn('15 рабочих дней',result['deadline_condition']);self.assertIn('п. 3.2',result['deadline_condition']);self.assertNotIn('1.5.',result['deadline_condition']);self.assertEqual('Старое название',self.data['positions'][0]['name'])
 def test_changed_document_requires_review(self):
  with self.assertRaises(ValueError):w.apply(self.data,TEXT.replace('90000','95000')+'changed')
 def test_money_quantity_kind_and_name_are_not_bypassed(self):
  for field,value in [('total','89000'),('quantity','2'),('kind','material'),('name','проектирование СС')]:
   row=w.apply(self.data,TEXT)['positions'][0];row[field]=value
   with self.subTest(field=field),self.assertRaises(ValueError):validate_contract_rows(TEXT,[row])
 def test_multiple_rows_rejected(self):
  row=w.apply(self.data,TEXT)['positions'][0]
  with self.assertRaises(ValueError):validate_contract_rows(TEXT,[row,row])
 def test_regular_specification_unchanged(self):self.assertEqual(self.data,w.apply(self.data,'ДОГОВОР № 7'))
if __name__=='__main__':unittest.main()
