import copy,json,tempfile,unittest
from pathlib import Path
import procurement_specs as s
import procurement_match as m
class SpecsTests(unittest.TestCase):
 def deal(self):
  return {'id':'1','positions':[{'id':'r','quantity':5,'sum':{'value':500},'unit':{'id':'u'},'offer':{'id':'o','name':'Кабель','type':'product','Category1000045CustomFieldTsenaZakupki':{'value':20}}}]}
 def test_import_without_local_spec_resolves_real_unit(self):
  rows=s.merge(self.deal(),[],{'u':'м'})
  self.assertEqual(rows[0]['unit'],'м');self.assertEqual(rows[0]['sell_price'],100)
 def test_refresh_preserves_cumulative_allocations_and_uses_row_id(self):
  old=[{'offer_row_id':'r','offer_id':'o','qty':5,'consumed_qty':2,'cumulative_cost_material':30,'cost_material':6}]
  r=s.merge(self.deal(),old,{'u':'м'})[0];self.assertEqual(r['consumed_qty'],2);self.assertEqual(r['cumulative_cost_material'],30);self.assertEqual(r['cost_material'],20)
  d=self.deal();d['positions'][0]['id']='new'
  with self.assertRaisesRegex(ValueError,'удалена'):s.merge(d,old,{'u':'м'})
 def test_quantity_reduction_cannot_lose_purchases(self):
  with self.assertRaisesRegex(ValueError,'меньше'):s.merge(self.deal(),[{'offer_row_id':'r','offer_id':'o','consumed_qty':6}],{'u':'м'})
 def test_missing_units_block_silent_allocation(self):
  with self.assertRaisesRegex(ValueError,'единица'):s.merge(self.deal(),[],{})
 def test_runtime_loads_missing_ledger_and_keeps_empty_deal_explicit(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);(root/'data').mkdir();ld=root/'ledger';ld.mkdir();proc=root/'proc.json';proc.write_text(json.dumps({'invoices':[{'candidate_deal_ids':['1','2']}]}))
   (root/'data/review_registry.json').write_text('{}');outer=self
   class API:
    def _call(self,method,path):
     assert method=='GET'
     return {'data':[{'id':'u','name':'м'}] if path=='/unit' else outer.deal() if path=='/deal/1' else {'id':'2','positions':[]}}
   result=s.refresh(API(),root=root,procurement_path=proc,ledger_dir=ld)
   self.assertEqual(result['1']['state'],'ready');self.assertIn('нет позиций',result['2']['error']);self.assertTrue((ld/'1.json').exists());self.assertEqual(s.refresh(API(),root=root,procurement_path=proc,ledger_dir=ld),{})
 def test_service_is_not_a_material_candidate(self):
  reg={'invoices':[{'document_key':'k','candidate_deal_ids':['1']}],'unallocated_stock':[{'id':'s','document_key':'k','available_qty':1,'initial_qty':1,'source_line_key':'1','name':'Кабель','unit':'м'}]}
  inputs,_=m.candidates(reg,{'1':[{'offer_row_id':'r','name':'Кабель','qty':1,'position_type':'service'}]});self.assertEqual(inputs,{})
if __name__=='__main__':unittest.main()

class InvoiceNumbersTests(unittest.TestCase):
 def test_integer_and_excel_amounts_are_not_rejected(self):
  import procurement_intake as intake
  for text in ('Итого 22 924 руб.','Сумма | 22924 | НДС', 'Сумма 22924.0'):
   result={'total_cents':2292400,'lines':[{'line_no':1,'name':'Блок','unit':'шт','qty':'1','amount_cents':2292400}]}
   intake.validate(result,{},text)
 def test_amount_must_be_a_whole_token(self):
  import procurement_intake as intake
  result={'total_cents':190100,'lines':[{'line_no':1,'name':'Блок','unit':'шт','qty':'1','amount_cents':190100}]}
  with self.assertRaisesRegex(ValueError,'не найдена'):intake.validate(result,{},'Сумма 11901.00')

class LegacyUsageTests(unittest.TestCase):
 def test_old_invoice_coverage_limits_new_candidates_even_without_ledger_counter(self):
  reg={'invoices':[{'document_key':'k','candidate_deal_ids':['1'],'allocations':[{'deal_id':'1','source_lines':[{'offer_row_id':'r','qty_used':5,'amount_used':100}]}]}],'unallocated_stock':[{'id':'s','document_key':'k','available_qty':1,'initial_qty':1,'source_line_key':'1','name':'Кабель','unit':'м'}]}
  self.assertEqual(m.candidates(reg,{'1':[{'offer_row_id':'r','name':'Кабель','qty':5,'unit':'м'}]})[0],{})
 def test_preview_cannot_double_allocate_legacy_quantity(self):
  import allocation_apply as a
  plan={'allocations':[{'deal_id':'1','qty':1,'name':'Кабель','offer_row_id':'r','identity_confirmed':True,'reason':'same'}]}
  entries={'1':[{'offer_row_id':'r','offer_id':'o','name':'Кабель','qty':5}]}
  with self.assertRaisesRegex(ValueError,'оставшегося'):a.targets(plan,entries,{('1','r'):{'qty':5,'cost':100}})

class AddedReceiptTests(unittest.TestCase):
 def test_existing_addition_becomes_source_link_without_new_cost(self):
  import procurement_intake as i
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'p.json';line={'line_no':1,'name':'Пульт C1G','unit':'шт','qty':'1','amount_cents':2760000,'key':'1:x'}
   data={'invoices':[{'id':'i','document_key':'k','number':'1624','total':27600,'intake':{'state':'review'},'lines':[line],'allocations':[{'deal_id':'1','amount':27600,'additions':[{'name':'Пульт C1G','qty':1,'cost_material':27600}]}]}],'unallocated_stock':[]}
   p.write_text(json.dumps(data));loader=lambda _:[{'offer_id':'o','offer_row_id':'r','name':'Пульт C1G','qty':1}]
   self.assertEqual(i.restore_added_receipts(p,loader),['k']);after=json.loads(p.read_text());a=after['invoices'][0]
   self.assertEqual(a['allocations'][0]['amount'],27600);self.assertEqual(a['allocations'][0]['source_lines'][0]['offer_row_id'],'r');self.assertEqual(a['intake']['state'],'ready');self.assertEqual(after['unallocated_stock'],[]);self.assertEqual(i.restore_added_receipts(p,loader),[])

class BundleReceiptTests(unittest.TestCase):
 def data(self):
  lines=[{'line_no':n,'name':name,'sku':sku,'key':str(n)+':'+sku.lower(),'unit':'шт','qty':'1','amount_cents':amount} for n,name,sku,amount in [(1,'Наружный блок','OUT-1',6000),(2,'Внутренний блок','IN-1',4000)]]
  return {'invoices':[{'id':'i','document_key':'k','total':100,'intake':{'state':'review'},'lines':lines,'allocations':[{'deal_id':'1','amount':100,'updates':[{'offer_row_id':'r','offer_id':'o','qty_used':1,'material_cost_used':100}]}]}],'unallocated_stock':[]}
 def test_bundle_restores_two_source_rows_one_kit_and_cost_once(self):
  import procurement_intake as i
  from procurement_usage import totals
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'p.json';p.write_text(json.dumps(self.data()))
   loader=lambda _:[{'offer_row_id':'r','supplier_sku':'IN-1/OUT-1'}]
   self.assertEqual(i.restore_bundle_receipts(p,loader),['k']);after=json.loads(p.read_text());inv=after['invoices'][0]
   self.assertEqual(inv['intake']['state'],'ready');self.assertEqual(totals(after)[('1','r')]['qty'],1);self.assertEqual(totals(after)[('1','r')]['cost'],100)
   self.assertEqual(sum(l['source_qty_used'] for l in inv['allocations'][0]['source_lines']),2)
   self.assertEqual(after['unallocated_stock'],[]);self.assertEqual(i.restore_bundle_receipts(p,loader),[])
 def test_mismatched_sku_cannot_be_repaired_by_name(self):
  import procurement_intake as i
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'p.json';p.write_text(json.dumps(self.data()));before=p.read_bytes()
   self.assertEqual(i.restore_bundle_receipts(p,lambda _:[{'offer_row_id':'r','supplier_sku':'IN-2/OUT-1'}]),[]);self.assertEqual(p.read_bytes(),before)
 def test_manual_split_cannot_duplicate_kit_or_change_cost(self):
  import procurement_intake as i
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'p.json';p.write_text(json.dumps(self.data()));before=p.read_bytes()
   parts=[{'line_no':n,'source_qty':1,'covered_qty':1,'amount_cents':amount,'reason':'компонент'} for n,amount in [(1,6000),(2,4000)]]
   with self.assertRaisesRegex(ValueError,'Количество комплектов'):i.repair_usage('k',{'split:0:0':parts},p)
   self.assertEqual(p.read_bytes(),before)
   parts[1]['covered_qty']=0;parts[1]['amount_cents']=3000
   with self.assertRaisesRegex(ValueError,'Суммы компонентов'):i.repair_usage('k',{'split:0:0':parts},p)
   self.assertEqual(p.read_bytes(),before)

class HistoricalBasisTests(unittest.TestCase):
 def test_refresh_does_not_turn_total_cost_into_unit_cost(self):
  row=s.merge(SpecsTests().deal(),[{'offer_row_id':'r','offer_id':'o','cost_material_basis':'line_total','cost_work_basis':'line_total'}],{'u':'м'})[0]
  self.assertEqual(row['cost_material_basis'],'line_total');self.assertEqual(row['cost_work_basis'],'line_total')

class ForeignInvoiceTests(unittest.TestCase):
 def test_foreign_original_converted_with_agreed_rate_and_audited_rounding(self):
  import procurement_intake as i
  inv={'number':'FX','currency':'EUR','foreign_total':.02,'plan_rate':1.5,'total':.03}
  parsed={'total_cents':2,'lines':[{'line_no':n,'name':'Блок '+str(n),'sku':str(n),'qty':'1','unit':'шт','amount_cents':1} for n in [1,2]]}
  result=i.convert_source(parsed,inv);self.assertEqual(result['total_cents'],3);self.assertEqual(sum(l['amount_cents'] for l in result['lines']),4);self.assertEqual(result['currency_conversion']['rounding_cents'],1)
  result['lines'][0]['amount_cents']+=1
  with self.assertRaisesRegex(ValueError,'Сумма строк'):i.validate(result,{})
 def test_currency_cannot_be_compared_to_rubles_or_use_unconfirmed_rate(self):
  import procurement_intake as i
  inv={'number':'FX','currency':'EUR','foreign_total':100,'plan_rate':90,'total':9000}
  self.assertEqual(i.source_meta(inv)['amount_cents'],10000)
  inv.pop('plan_rate')
  with self.assertRaisesRegex(ValueError,'согласованный курс'):i.source_meta(inv)

class ServiceClassificationTests(unittest.TestCase):
 def test_maintenance_is_work_not_a_missing_material_purchase(self):
  from position_types import name_kind
  self.assertEqual(name_kind('Техническое обслуживание кондиционера'),'work')

class CrmCurrencyTests(unittest.TestCase):
 def test_mixed_currency_deal_uses_net_ruble_equivalent_including_discount(self):
  from megaplan_api import MegaplanAPI
  deal={'positions':[{'id':'r','quantity':85,'offer':{'id':'o','name':'Труба','type':'product'},'price':{'currency':'USD','value':36,'valueInMain':3019.23},'sum':{'currency':'USD','value':2907,'valueInMain':243802.8225}}]}
  row=MegaplanAPI.ledger_from_deal(deal)[0]
  self.assertAlmostEqual(row['sell_price']*85,243802.8225);self.assertEqual(row['list_price'],3019.23)
 def test_zero_conversion_and_missing_rate_are_distinguished(self):
  from financial_amounts import crm_money_in_main
  self.assertEqual(crm_money_in_main({'currency':'USD','value':100,'valueInMain':0}),0)
  self.assertEqual(crm_money_in_main({'currency':'USD','value':2,'rate':85}),170)
  with self.assertRaisesRegex(ValueError,'эквивалента'):crm_money_in_main({'currency':'USD','value':100})

class SharedRegistryTests(unittest.TestCase):
 def test_bank_sync_preserves_spec_refresh_and_pending_document_command(self):
  import review_registry as q
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);(root/'data').mkdir();path=root/'data/review_registry.json'
   state={'tasks':{},'historical_answers':[],'followups_migrated':True,'procurement_specs':{'1':{'state':'queued','attempts':0}},'procurement_commands':{'invoice':{'state':'processing','id':'job'}}}
   path.write_text(json.dumps(state));after=q.sync([],root,{'invoices':[]})
   self.assertEqual(after['procurement_specs'],state['procurement_specs']);self.assertEqual(after['procurement_commands'],state['procurement_commands'])

class LegacySourceDiscoveryTests(unittest.TestCase):
 def test_complete_original_recovers_legacy_source_but_ambiguous_versions_do_not(self):
  import procurement_intake as i
  from unittest.mock import patch
  with tempfile.TemporaryDirectory() as d:
   base=Path(d);root=base/'finance';crm=base/'crm';(root/'evidence/deep_review').mkdir(parents=True);crm.mkdir()
   original=base/'original.pdf';original.write_bytes(b'original');other=base/'other.pdf';other.write_bytes(b'other version')
   (crm/'procurement_registry.json').write_text(json.dumps({'invoices':[{'number':'N-1','supplier':'Vendor','supplier_inn':'1234567890','total':12,'allocations':[{'deal_id':'9'}]}]}))
   index=root/'evidence/deep_review/additional_documents.json';index.write_text(json.dumps([{'path':str(original),'text':'N-1'}]))
   text='ИНН 1234567890 Счет N-1\nКод товара ЭТМ\n 1 ETM1 Кабель С м 2 10.00 2.00 12.00\n'
   with patch.object(i,'extract',return_value=text):
    rows=i.discover(root,crm);self.assertEqual(len(rows),1);self.assertEqual(rows[0]['deal_ids'],['9']);self.assertEqual(rows[0]['amount_cents'],1200)
    index.write_text(json.dumps([{'path':str(original),'text':'N-1'},{'path':str(other),'text':'N-1'}]));self.assertEqual(i.discover(root,crm),[])

class ArchiveDiscoveryTests(unittest.TestCase):
 def test_archive_originals_are_downloaded_once_with_bounded_cycle(self):
  import hashlib
  import procurement_intake as i
  with tempfile.TemporaryDirectory() as d:
   root=Path(d)/'finance';crm=Path(d)/'crm';(root/'reports').mkdir(parents=True);crm.mkdir();entries=[];bank=[]
   for n in range(3):
    filename=str(n)+'.pdf';entries.append({'category':'supplier_invoice','status':'uploaded','document_number':'212-'+str(n),'filename':filename,'sha256':hashlib.sha256(filename.encode()).hexdigest(),'deal_id':'9','onedrive_remote':'fixture'})
    bank.append({'id':str(n),'inn':'1234567890','counterparty':'Поставщик','direction':'out','document_numbers':'212/'+str(n),'amount_cents':100,'date':'2026-01-01','confirmed_payment_allocations':[{'deal_id':'9','amount_cents':100,'invoice_number':'212/'+str(n)}]})
   (crm/'financial_archive.json').write_text(json.dumps({'documents':entries}));(root/'reports/ledger.json').write_text(json.dumps(bank));calls=[]
   def download(entry,target):
    calls.append(entry['filename']);target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(entry['filename'].encode())
   self.assertEqual(len(i.discover(root,crm,download)),2);self.assertEqual(len(calls),2)
   self.assertEqual(len(i.discover(root,crm,download)),3);self.assertEqual(len(calls),3)
   self.assertEqual(len(i.discover(root,crm,download)),3);self.assertEqual(len(calls),3)

class GoodsDiscountTests(unittest.TestCase):
 def sample(self):
  return 'Счет № 208096 от 23.06.2026\nТовары (работы, услуги)\n 1  00-001  Товар A                     3 шт      100,00      300,00\n 2  00-002  Товар Б                     1 шт      100,00      100,00\n 3  00-003  Доставка товара                 Услуга     50,00       50,00\n Скидка: 100,01\n Всего к оплате: 349,99\n'
 def test_policy_required_and_services_not_discounted(self):
  import procurement_intake as p
  with self.assertRaisesRegex(ValueError,'отличается'):p.parse(self.sample(),{'number':'208096'})
  r=p.parse(self.sample(),{'number':'208096','discount_policy':'goods_only'})
  self.assertEqual([l['amount_cents'] for l in r['lines']],[22499,7500,5000]);self.assertEqual(sum(l['discount_cents'] for l in r['lines']),10001)
  self.assertEqual(r['lines'][-1]['discount_cents'],0)
 def test_tampering_cannot_pass_by_keeping_total(self):
  import procurement_intake as p
  r=p.parse(self.sample(),{'discount_policy':'goods_only'});r['lines'][0]['amount_cents']+=1;r['lines'][1]['amount_cents']-=1
  with self.assertRaisesRegex(ValueError,'распределение скидки'):p.validate(r,{},self.sample())
 def test_discount_must_be_in_source_and_explain_total(self):
  import procurement_intake as p
  with self.assertRaisesRegex(ValueError,'не объясняет'):p.parse(self.sample().replace('349,99','340,00'),{'discount_policy':'goods_only'})
  r=p.parse(self.sample(),{'discount_policy':'goods_only'})
  with self.assertRaisesRegex(ValueError,'Скидка не найдена'):p.validate(r,{},self.sample().replace('Скидка: 100,01','Скидка: 99,00'))
 def test_multiple_cent_remainder_and_no_negative_goods(self):
  import procurement_intake as p
  r={'total_cents':1,'lines':[{'line_no':n,'name':'Товар','unit':'шт','amount_cents':1} for n in range(1,4)]}
  out=p.allocate_goods_discount(r,2);self.assertEqual([x['amount_cents'] for x in out['lines']],[0,0,1]);self.assertEqual(r['lines'][0]['amount_cents'],1)
  with self.assertRaises(ValueError):p.allocate_goods_discount(r,4)
