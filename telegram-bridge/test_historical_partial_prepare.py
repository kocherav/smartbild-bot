import copy,tempfile,unittest
from pathlib import Path
from unittest.mock import Mock,patch
from contextlib import ExitStack
import closing_runtime as c
import partial_shipments as p
from closing_workflow import Registry

class HistoricalPrepareTests(unittest.TestCase):
 def run_prepare(self,day,rate=-1,payment=None,ip=False):
  import contract_invoice,generate_contract,document_tax_policy,closing_documents,hogart_closing,procurement_attachments,procurement_workflow
  from docx import Document
  with tempfile.TemporaryDirectory() as directory,ExitStack() as stack:
   base=Path(directory);reg=Registry(base/'jobs.json');j=reg.enqueue('7',mode='test')
   row={'id':'1','name':'Товар','kind':'equipment','unit':'шт.','quantity':2,'unit_price':50,'total':100,'tax_rate':rate}
   data={'deal_id':'7','number':'1.7','date':'01.09.2026','contract_date_iso':'2026-09-01','address':'Адрес','payer_id':'p','payer_name':'Клиент','payer':{'inn':'123','kpp':'456','contractor':{'id':'99'}},'signatory':{'position':'Директор','name':'Иванов Иван Иванович','authority':'Устав'},'positions':[row],'total':100,'missing':[]}
   deal={'id':'7','state':{'id':'136'},'payer':{'id':'p'},'price':{'value':100},'financeOperations':[],'financeOperationsCount':0,'positions':[{'id':'1','tax':{'rate':rate}}]}
   selected={**row,'quantity':'1','total':'50.00','unit_price':'50.00'}
   job=reg.patch(j['id'],shipment_id=j['id'],shipment={'positions':[selected],'total':'50.00','source':{'total':'100.00'},'act_number':'7-АПП/01','transfer_date':day,'payment':payment or {}})
   crm=Mock();crm._call.side_effect=lambda method,path,**kw:{'data':data['payer'] if path.startswith('/payer/') else deal}
   source=base/'contract.pdf';source.write_bytes(b'fixture')
   text='СПЕЦИФИКАЦИЯ\nТовар    шт.  2  50,00  100,00\n40702810902570001580 044525593 30101810200000000593'
   seller={'id':'cliwell','inn':'7743151323','accounts':['40702810902570001580']}
   if ip:
    from PIL import Image
    image=base/'sig.png';Image.new('RGBA',(20,10),(0,0,0,255)).save(image)
    seller={'id':'kocherzhinsky_ip','name':'ИП Кочержинский А.В.','legal_name':'Индивидуальный предприниматель Кочержинский Артем Вадимович','inn':'782093991468','ogrnip':'324774600759551','accounts':['40802810300007034866'],'bank':{'bik':'044525974','correspondent_account':'30101810145250000974'},'signatory':{'name':'Кочержинский Артем Вадимович'},'signature_image':str(image)}
    text=text.replace('40702810902570001580 044525593 30101810200000000593','40802810300007034866 044525974 30101810145250000974')
   def convert(*args,**kw):
    Path(args[0][-1]).with_suffix('.pdf').write_bytes(b'%PDF fixture');return Mock(returncode=0)
   patches=[patch.object(c,'REGISTRY',base/'jobs.json'),patch.object(c,'OUT',base),patch.object(c,'api',return_value=crm),patch.object(c,'sources',return_value=[]),patch.object(c,'deadline',return_value='30.10.2026'),patch.object(p,'validate',return_value=deal),patch.object(generate_contract,'contract_data',return_value=copy.deepcopy(data)),patch.object(contract_invoice,'latest_contract',return_value=({'id':'file'},str(source))),patch.object(contract_invoice,'document_text',return_value=text),patch.object(contract_invoice,'preview',side_effect=AssertionError('Full invoice preview must not run')),patch.object(document_tax_policy,'require_document_tax',side_effect=AssertionError('Today/full-deal tax gate must not run')),patch.object(document_tax_policy,'settings',return_value={'companies':{'cliwell':[{'from':'2020-01-01','rate':-1},{'from':'2026-10-01','rate':5}]}}),patch.object(hogart_closing,'sync',return_value=[]),patch.object(procurement_attachments,'build',return_value={'files':[],'attachments':[],'register':''}),patch.object(procurement_workflow,'supplier_invoices_for_deal',return_value=[]),patch.object(procurement_workflow,'accounting_hints',return_value={'hints':[]}),patch.object(closing_documents.subprocess,'run',side_effect=convert),patch('seller_documents.selected_seller',return_value=seller)]
   for item in patches:stack.enter_context(item)
   updated=c.prepare(job)
   doc=Document(next((base/job['id']).glob('ТЕСТ — Акт_*.docx')));body='\n'.join(x.text for x in doc.paragraphs)
   return updated,body
 def test_september_prepare_passes_without_today_tax_or_full_invoice(self):
  job,text=self.run_prepare('30.09.2026')
  self.assertEqual('ready',job['status']);self.assertEqual('30.09.2026',job['data']['transfer_dates']['goods'])
  self.assertIn('Дата передачи товаров: 30.09.2026',text);self.assertNotIn('Окончательный расчёт:',text)
  self.assertEqual(2,len(job['documents']));self.assertNotIn('работы — 30.09.2026 с НДС 5%',job['note'])
  import shipment_finance
  plan=shipment_finance.plans({**job,'mode':'live'})[0]
  self.assertEqual('2026-09-30',plan['date']);self.assertEqual(5000,plan['amount_cents']);self.assertEqual('0.00',shipment_finance.form(plan)['Model[Sum][Value]'])
 def test_ip_partial_prepare_uses_seller_bank_and_no_advance_deadline(self):
  with patch.object(c,'deadline',side_effect=AssertionError('Partial transfer does not require final deadline')):
   job,text=self.run_prepare('30.09.2026',ip=True)
  self.assertEqual(job['status'],'ready');self.assertEqual(job['data']['seller']['id'],'kocherzhinsky_ip')
  self.assertEqual(job['data']['act_date'],'30.09.2026');self.assertIsNone(job['data']['deadline'])
  self.assertIn('782093991468',job['note']);self.assertIn('Индивидуальный предприниматель Кочержинский',text)
  self.assertEqual(len(job['documents']),2)
 def test_october_no_vat_is_still_blocked(self):
  with self.assertRaisesRegex(ValueError,'ставке НДС'):self.run_prepare('01.10.2026')
 def test_october_five_percent_is_allowed(self):
  job,_=self.run_prepare('01.10.2026',5);self.assertEqual('ready',job['status'])

class PartialPaymentContextTests(unittest.TestCase):
 def test_optional_invoice_uses_selected_rows_and_never_final_amount(self):
  job={'shipment':{'positions':[{'tax_rate':-1}],'transfer_date':'30.09.2026','act_number':'7-АПП/01','payment':{'amount':'25.00','clause':'6.4.2','basis':'Оплата переданной части'}}}
  result=p.payment_context(job,'6.4.2 Окончательный расчёт 1 650 000,00 руб.')
  self.assertEqual('25.00',result['amount']);self.assertEqual(-1,result['tax_rate']);self.assertNotIn('1 650 000',result['line'])
  with self.assertRaisesRegex(ValueError,'не найден'):p.payment_context(job,'6.4.3 Другой пункт')
 def test_bank_cash_and_goods_are_not_confused(self):
  deal={'id':'7','price':{'value':7650000},'financeOperationsCount':3,'financeOperations':[{'id':'1','kind':'income','type':{'id':'31'},'incomeSum':{'value':4500000},'date':{'value':'2026-07-01T12:00:00+00:00'}},{'id':'2','kind':'income','type':{'id':'31'},'incomeSum':{'value':1000000},'date':{'value':'2026-07-01T12:00:00+00:00'}},{'id':'3','kind':'income','type':{'id':'31'},'incomeSum':{'value':0},'date':{'value':'2026-09-30T12:00:00+00:00'},'goodsSum':{'value':200000}}]}
  
  for operation in deal['financeOperations']:operation['incomeSum']['currency']='RUB'
  paid,proof=p.payment_summary(deal);self.assertEqual(550000000,paid)
  deal['financeOperationsCount']=4
  with self.assertRaisesRegex(ValueError,'сверить'):p.payment_summary(deal)

class AdvanceDeadlineTests(unittest.TestCase):
 def test_named_advance_without_clause_number_must_match_contract_amount(self):
  text='ДОГОВОР № 1.861\n30.06.2026\n6.4.1 Предоплата, что составляет 4 500 000,00(четыре миллиона) рублей.\n6.4.2 Окончательный платёж.\nСПЕЦИФИКАЦИЯ 60 (шестьдесят) рабочих дней'
  tx={'direction':'income','purpose':'Авансовый платёж по договору 1.861','date':'01.07.2026','amount':'4500000.00'}
  self.assertEqual('23.09.2026',c.deadline(text,[tx]))
  with self.assertRaises(ValueError):c.deadline(text,[{**tx,'amount':'1000000.00'}])
  with self.assertRaises(ValueError):c.deadline(text,[{**tx,'purpose':'Окончательный расчёт'}])

class ShipmentIdentityTests(unittest.TestCase):
 def test_employee_online_status_does_not_change_document_identity(self):
  a={'id':'p','name':'Клиент','inn':'123','currentAccount':'111','contractor':{'id':'99','responsibles':[{'lastOnline':{'value':'now'}}]}}
  b=copy.deepcopy(a);b['contractor']['responsibles'][0]['lastOnline']['value']='later'
  self.assertEqual(p.document_payer(a),p.document_payer(b))
  b['currentAccount']='222';self.assertNotEqual(p.document_payer(a),p.document_payer(b))
  b=copy.deepcopy(a);b['contractor']['id']='100';self.assertNotEqual(p.document_payer(a),p.document_payer(b))

class ShipmentRoundingTests(unittest.TestCase):
 def test_subkopeck_rows_keep_grand_total_and_allow_complete_remainder(self):
  from decimal import Decimal
  data={'total':'3.01','positions':[{'id':str(i),'quantity':1,'total':'1.004','kind':'equipment','name':'Товар','unit':'шт.','tax_rate':-1} for i in range(3)]}
  p.round_document_rows(data)
  self.assertEqual(Decimal('3.01'),sum(Decimal(str(r['total'])) for r in data['positions']))
  selected=p.workspace.select(data,[{'id':r['id'],'quantity':1} for r in data['positions']],[])
  self.assertEqual(Decimal('3.01'),sum(Decimal(r['total']) for r in selected))
  self.assertEqual(['1.01','1.00','1.00'],[r['total'] for r in data['positions']])
  data['total']='4.00'
  with self.assertRaisesRegex(ValueError,'сумм'):p.round_document_rows(data)
