import io,tempfile,unittest
from pathlib import Path
from unittest.mock import Mock,patch
import contract_invoice as c
from closing_documents import validate_contract_rows
class CustomerContractSelectionTests(unittest.TestCase):
 def setUp(self):
  directory=tempfile.TemporaryDirectory();self.addCleanup(directory.cleanup)
  patched=patch.object(c,'CONTRACT_SOURCES',Path(directory.name));patched.start();self.addCleanup(patched.stop)
 def file(self,i,name):return {'id':str(i),'name':name,'path':'/file/'+str(i),'timeCreated':{'value':str(i)}}
 def test_new_supplier_invoice_contract_does_not_replace_customer_contract(self):
  api=Mock(domain='test.megaplan.ru',token='fixture');api._call.return_value={'data':[self.file(3,'Элрус_Счет_договор_61810.pdf'),self.file(2,'Договор КЛИВЭЛ.docx')]}
  with patch.object(c.megaplan_transport,'urlopen',return_value=io.BytesIO(b'customer')) as download:
   selected,path=c.latest_contract(api,'861');self.assertEqual(selected['id'],'2');Path(path).unlink();self.assertEqual(download.call_count,1)
 def test_generic_wrong_party_document_is_skipped_by_context(self):
  api=Mock(domain='test.megaplan.ru',token='fixture');api._call.return_value={'data':[self.file(3,'Договор поставщика.pdf'),self.file(2,'Договор клиента.pdf')]}
  texts=['ДОГОВОР № other\nИНН 1111111111 2222222222','ДОГОВОР № 1.861\nИНН 1111111111 3333333333']
  with patch.object(c.megaplan_transport,'urlopen',side_effect=[io.BytesIO(b'a'),io.BytesIO(b'b')]),patch.object(c,'document_text',side_effect=texts):
   selected,path=c.latest_contract(api,'861',{'number':'1.861','seller_inn':'1111111111','payer_inn':'3333333333'});self.assertEqual(selected['id'],'2');Path(path).unlink()
 def test_work_contract_header_is_not_silently_replaced_by_old_template(self):
  api=Mock(domain='test.megaplan.ru',token='fixture');api._call.return_value={'data':[self.file(3,'Договор подряда.pdf'),self.file(2,'Договор типовой.docx')]}
  texts=['ДОГОВОР ПОДРЯДА № 1.846-0104/2026\nИНН 7743151323 7733356410','ДОГОВОР № 1.846-0104/2026\nИНН 7743151323 7733356410']
  with patch.object(c.megaplan_transport,'urlopen',side_effect=[io.BytesIO(b'a'),io.BytesIO(b'b')]),patch.object(c,'document_text',side_effect=texts):
   selected,path=c.latest_contract(api,'846',{'number':'1.846-0104/2026','seller_inn':'7743151323','payer_inn':'7733356410'})
   self.addCleanup(lambda:Path(path).unlink(missing_ok=True));self.assertEqual('3',selected['id'])
 def test_customer_contract_on_second_file_page(self):
  api=Mock(domain='test.megaplan.ru',token='fixture');api._call.side_effect=[{'data':[self.file(3,'Счет-договор.pdf')],'meta':{'pagination':{'hasMoreNext':True}}},{'data':[self.file(2,'Договор.docx')]}]
  with patch.object(c.megaplan_transport,'urlopen',return_value=io.BytesIO(b'a')):
   selected,path=c.latest_contract(api,'861');Path(path).unlink();self.assertEqual(selected['id'],'2');self.assertEqual(api._call.call_count,2)
 def test_docx_vertical_cells_are_supported_but_wrong_total_rejected(self):
  text='Спецификация\nТестовый корпус\nшт.\n2\n47\u00a0360,40 руб.\n71\u00a0040,60 руб.\n'
  rows=[{'id':'1','name':'Тестовый корпус','quantity':2,'total':'71040.60'}]
  self.assertEqual(validate_contract_rows(text,rows)[0]['unit'],'шт.')
  rows[0]['total']='70000.00'
  with self.assertRaisesRegex(ValueError,'сумма'):validate_contract_rows(text,rows)

 def test_specification_validation_preserves_deal_unit_label(self):
  text='Спецификация\nКабель\nм\n2\n50,00 руб.\n100,00 руб.\n'
  rows=[{'id':'1','name':'Кабель','unit':'пог. м','quantity':2,'total':'100'}]
  self.assertEqual('пог. м',validate_contract_rows(text,rows)[0]['unit'])

 def test_rejected_draft_is_not_reused_after_owner_confirmed_total(self):
  api=Mock(domain='test.megaplan.ru',token='fixture');api._call.return_value={'data':[self.file(2,'Договор клиента.docx')]}
  with tempfile.TemporaryDirectory() as directory:
   Path(directory,'861-source.json').write_text('{"confirmed_total":"7650000.00","rejected_file_ids":["2"]}')
   with patch.object(c,'CONTRACT_SOURCES',Path(directory)),patch.object(c.megaplan_transport,'urlopen') as download:
    with self.assertRaisesRegex(ValueError,'7 650 000,00'):c.latest_contract(api,'861')
    download.assert_not_called()

 def test_pdf_currency_suffix_is_not_a_missing_specification(self):
  text='СПЕЦИФИКАЦИЯ\nКабель    м    2    50,00 руб.    100,00 руб.\n'
  rows=[{'id':'1','name':'Кабель','unit':'м','quantity':2,'total':'100'}]
  self.assertEqual('100.00',validate_contract_rows(text,rows)[0]['total'])

 def test_supplemental_scope_checks_exact_owner_approved_amount(self):
  rows=[{'id':'1','name':'Товар','quantity':1,'total':100},{'id':'2','name':'Монтаж','quantity':1,'total':50}]
  with tempfile.TemporaryDirectory() as directory:
   Path(directory,'861-source.json').write_text('{"supplemental_rows":{"2":{"name":"Монтаж","quantity":"1","total":"50"}}}')
   with patch.object(c,'CONTRACT_SOURCES',Path(directory)):
    self.assertEqual(['1'],[r['id'] for r in c.contract_scope(rows,'861')])
    rows[1]['total']=51
    with self.assertRaisesRegex(ValueError,'дополнительных'):c.contract_scope(rows,'861')

 def test_pinned_contract_wins_over_newer_draft_and_hash_is_checked(self):
  import json,hashlib
  api=Mock(domain='test.megaplan.ru',token='fixture');api._call.return_value={'data':[self.file(3,'Договор черновик.docx'),self.file(2,'Договор.pdf')]}
  with tempfile.TemporaryDirectory() as directory:
   Path(directory,'861-source.json').write_text(json.dumps({'signed_file_id':'2','sha256':hashlib.sha256(b'signed').hexdigest()}))
   with patch.object(c,'CONTRACT_SOURCES',Path(directory)),patch.object(c.megaplan_transport,'urlopen',return_value=io.BytesIO(b'signed')):
    chosen,path=c.latest_contract(api,'861');self.assertEqual('2',chosen['id']);Path(path).unlink()
   with patch.object(c,'CONTRACT_SOURCES',Path(directory)),patch.object(c.megaplan_transport,'urlopen',return_value=io.BytesIO(b'changed')):
    with self.assertRaisesRegex(ValueError,'Содержимое'):c.latest_contract(api,'861')

 def test_missing_pinned_contract_cannot_fall_back_to_draft(self):
  api=Mock(domain='test.megaplan.ru',token='fixture');api._call.return_value={'data':[self.file(3,'Договор черновик.docx')]}
  with tempfile.TemporaryDirectory() as directory:
   Path(directory,'861-source.json').write_text('{"signed_file_id":"2"}')
   with patch.object(c,'CONTRACT_SOURCES',Path(directory)),patch.object(c.megaplan_transport,'urlopen') as download:
    with self.assertRaisesRegex(ValueError,'подмена'):c.latest_contract(api,'861')
    download.assert_not_called()

 def test_included_materials_require_exact_document_and_one_exact_line(self):
  import json,hashlib
  text='СПЕЦИФИКАЦИЯ\nТовар    шт.  1  100,00 руб.  100,00 руб.\nРасходные материалы    к-т  1  20,00 руб.  20,00 руб.\n'
  with tempfile.TemporaryDirectory() as directory:
   source={'included_specification_lines':{'text_sha256':hashlib.sha256(text.encode()).hexdigest(),'lines':['Расходные материалы    к-т  1  20,00 руб.  20,00 руб.']}}
   Path(directory,'861-source.json').write_text(json.dumps(source))
   with patch.object(c,'CONTRACT_SOURCES',Path(directory)):
    result=c.specification_text(text,'861');self.assertNotIn('Расходные материалы',result);self.assertIn('Товар',result)
    self.assertEqual(text,c.specification_text(text,'862'))
    with self.assertRaisesRegex(ValueError,'редакция'):c.specification_text(text.replace('20,00','21,00'),'861')
    source['included_specification_lines']['lines']*=2;Path(directory,'861-source.json').write_text(json.dumps(source))
    with self.assertRaisesRegex(ValueError,'строка'):c.specification_text(text,'861')

class ServiceUnitRegression(__import__('unittest').TestCase):
 def test_mixed_goods_and_services_docx_and_pdf(self):
  rows=[{'name':'Товар','quantity':1,'total':'100.00','unit':'шт.'},{'name':'Опрессовка системы','quantity':2,'total':'17000.00','unit':'усл.'}]
  for text in ('СПЕЦИФИКАЦИЯ\nТовар\nшт.\n1\n100,00 руб.\n100,00 руб.\nОпрессовка системы\nусл.\n2\n8 500,00 руб.\n17 000,00 руб.', 'СПЕЦИФИКАЦИЯ\nТовар  шт. 1 100,00 100,00\nОпрессовка системы  усл. 2 8 500,00 17 000,00'):
   self.assertEqual(len(validate_contract_rows(text,rows)),2)
   changed=[rows[0],{**rows[1],'total':'16000.00'}]
   with self.assertRaisesRegex(ValueError,'сумма'):validate_contract_rows(text,changed)

class SpecificationUnitRegression(__import__('unittest').TestCase):
 def test_units_from_deal_in_both_document_layouts(self):
  for unit in ('кв.м','м²','м3','кг','л','пог. м','упак.','чел.-ч','рулон'):
   rows=[{'name':'Материал','quantity':96,'total':'19200','unit':unit}]
   for sep,prefix in (('\n','\n'),('  ','  ')):
    text='СПЕЦИФИКАЦИЯ\nМатериал'+prefix+sep.join((unit,'96','200,00 руб.','19\u00a0200,00 руб.'))
    with self.subTest(unit=unit,sep=sep):
     result=validate_contract_rows(text,rows)
     self.assertEqual(result[0]['unit'],unit)
     self.assertEqual(result[0]['total'],'19200.00')
     with self.assertRaisesRegex(ValueError,'Объём или сумма'):
      validate_contract_rows(text,[{**rows[0],'quantity':95}])
     with self.assertRaisesRegex(ValueError,'строк'):
      validate_contract_rows(text,rows*2)
 def test_missing_specification_is_explicit(self):
  with self.assertRaisesRegex(ValueError,'Не найдена спецификация'):
   validate_contract_rows('Договор без приложения',[])
 def test_full_heating_specification_59_rows(self):
  import json
  from decimal import Decimal
  from specification_unit_fixture import TEXT as text, ROWS as rows
  result=validate_contract_rows(text,rows)
  self.assertEqual(len(result),59)
  self.assertEqual(sum(Decimal(r['total']) for r in result),Decimal('3900000.00'))
  area=next(r for r in result if r['unit']=='кв.м')
  self.assertEqual(area['quantity'],96)
  self.assertEqual(area['total'],'19200.00')
 def test_mixed_layouts_are_not_partially_parsed(self):
  rows=[{'name':'Плёнка','unit':'м²','quantity':2,'total':100}, {'name':'Монтаж','unit':'усл.','quantity':1,'total':20}]
  text='СПЕЦИФИКАЦИЯ\nПлёнка  м² 2 50,00 100,00\nМонтаж\nусл.\n1\n20,00\n20,00'
  self.assertEqual(len(validate_contract_rows(text,rows)),2)
 def test_owner_pdf_reordered_rows_preserve_crm_order(self):
  from specification_unit_fixture import OWNER_PDF_TEXT,ROWS
  result=validate_contract_rows(OWNER_PDF_TEXT,ROWS)
  self.assertEqual([r['name'] for r in result],[r['name'] for r in ROWS])
  self.assertEqual([float(r['total']) for r in result],[float(r['total']) for r in ROWS])
  with self.assertRaises(ValueError):validate_contract_rows(OWNER_PDF_TEXT,[{**r,'total':1} for r in ROWS])
 def test_duplicate_names_not_guessed(self):
  rows=[{'name':'Товар','unit':'шт.','quantity':1,'total':10}]*2
  with self.assertRaises(ValueError):validate_contract_rows('СПЕЦИФИКАЦИЯ\nТовар  шт. 1 10,00 10,00\nТовар  шт. 1 10,00 10,00',rows)
