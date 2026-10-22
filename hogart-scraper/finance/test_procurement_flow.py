import copy,json,tempfile,unittest,sys
from pathlib import Path
from unittest.mock import patch
import procurement_intake as intake
import procurement_match as matching
import procurement_workspace as workspace
import allocation_apply as apply
import allocation_workspace as aw
from procurement_projection import effective_registry
class FlowTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name);(self.root/'data').mkdir();(self.root/'ledger').mkdir()
  self.path=self.root/'proc.json';self.path.write_text(json.dumps({'invoices':[],'unallocated_stock':[],'deals':{}}));(self.root/'data/review_registry.json').write_text(json.dumps({'tasks':{},'updated_at':'now'}))
  self.meta={'source':'fixture.pdf','number':'S1','supplier_inn':'123','buyer_inn':'456','sha256':'sha','deal_ids':['1'],'amount_cents':10000}
  self.parsed={'date':'01.10.2026','total_cents':10000,'lines':[{'line_no':1,'sku':'p','name':'Труба PPR Ø50','qty':'14','unit':'шт','amount_cents':10000}]}
  self.rows=[{'offer_row_id':'r','offer_id':'o','name':'Труба PPR Ø50','qty':56,'unit':'шт.','consumed_qty':0,'cumulative_cost_material':0,'cost_material':0,'sell_price':100,'cost_work':0}];(self.root/'ledger/1.json').write_text(json.dumps(self.rows))
  self.loader=lambda did:json.loads((self.root/'ledger'/f'{did}.json').read_text());self.deals=[{'id':'1','name':'Test'}]
 def imported(self):
  key=intake.register(self.meta,self.path);intake.install(key,copy.deepcopy(self.parsed),self.path);return key,json.loads(self.path.read_text())
 def test_import_idempotence_and_no_cash_or_crm_mutation(self):
  key,data=self.imported();intake.register(self.meta,self.path);intake.install(key,copy.deepcopy(self.parsed),self.path)
  again=json.loads(self.path.read_text());self.assertEqual(len(again['invoices']),1);self.assertEqual(len(again['unallocated_stock']),1);self.assertEqual(again['invoices'][0]['allocations'],[]);self.assertEqual(self.loader('1'),self.rows)
 def test_missing_row_links_generate_candidates(self):
  key,data=self.imported();options=matching.suggestions(data,{'1':self.rows},self.root/'matching.db')
  self.assertEqual(len(options),1);self.assertTrue(options[0]['approved']);self.assertEqual(options[0]['offer_row_id'],'r')
 def test_package_length_needs_human_conversion(self):
  self.parsed['lines'][0]['name']='Труба PPR Ø50 4м';key,data=self.imported();options=matching.suggestions(data,{'1':self.rows},self.root/'matching.db');self.assertTrue(options);self.assertFalse(options[0]['unit_compatible'])
 def test_manual_conversion_four_metre_pieces_to_contract_units(self):
  key,data=self.imported();line=data['unallocated_stock'][0];body={'document_key':key,'source_revision':aw.fingerprint(aw.source_document(data,key)),'allocations':[{'line_id':line['id'],'deal_id':'1','offer_row_id':'r','qty':14,'covered_qty':56,'identity_confirmed':True,'reason':'14 отрезков по 4 метра = 56'}]}
  plan=apply.prepare(body,self.deals,data,self.loader);job={'id':'job','actor':'test','plan':plan};apply.commit(job,self.path,self.root/'ledger')
  self.assertEqual(self.loader('1')[0]['consumed_qty'],56);self.assertEqual(self.loader('1')[0]['cumulative_cost_material'],100)
  inv=effective_registry(json.loads(self.path.read_text()))['invoices'][0];line=inv['allocations'][0]['source_lines'][0];self.assertEqual(line['qty_used'],56);self.assertEqual(line['source_qty_used'],14)
  apply.commit(job,self.path,self.root/'ledger');self.assertEqual(self.loader('1')[0]['consumed_qty'],56)
  from shipment_procurement import coverage
  result=coverage('1',[{'id':'r','name':'Труба PPR Ø50','quantity':56,'unit':'шт.'}],json.loads(self.path.read_text()))
  self.assertEqual(result['r']['state'],'full')
 def test_manual_target_requires_confirmation_and_capacity(self):
  key,data=self.imported();stock=data['unallocated_stock'][0];body={'document_key':key,'source_revision':aw.fingerprint(aw.source_document(data,key)),'allocations':[{'line_id':stock['id'],'deal_id':'1','offer_row_id':'r','qty':1,'covered_qty':1,'reason':'Проверено'}]}
  with self.assertRaisesRegex(ValueError,'Подтвердите'):apply.prepare(body,self.deals,data,self.loader)
  body['allocations'][0].update(identity_confirmed=True,covered_qty=57)
  with self.assertRaisesRegex(ValueError,'больше'):apply.prepare(body,self.deals,data,self.loader)
 def test_different_versions_cannot_create_automatic_duplicate(self):
  key,data=self.imported();other={**self.meta,'sha256':'newhash','amount_cents':15000};intake.register(other,self.path);result=json.loads(self.path.read_text());self.assertEqual(result['invoices'][1]['intake']['state'],'version_review');self.assertEqual(len(result['unallocated_stock']),1)
 def test_invalid_totals_rejected_and_historical_allocations_preserved(self):
  key,data=self.imported();parsed=copy.deepcopy(self.parsed);parsed['lines'][0]['amount_cents']=9999
  with self.assertRaises(ValueError):intake.install(key,parsed,self.path)
  self.assertEqual(json.loads(self.path.read_text()),data)
 def test_ambiguous_multiple_deals_never_auto_distributes(self):
  key,data=self.imported();data['invoices'][0]['candidate_deal_ids']=['1','2'];opts=matching.suggestions(data,{'1':self.rows,'2':self.rows},self.root/'matching.db');doc=aw.public_document(aw.source_document(data,key),{})
  self.assertEqual(matching.auto_parts(doc,opts),[])
 def test_document_command_persisted_and_stale_rejected(self):
  key,data=self.imported();body={'action':'retry','document_key':key,'source_revision':aw.fingerprint(aw.source_document(data,key))}
  result=workspace.command(body,7,self.root,self.path);self.assertEqual(result['state'],'queued')
  body['source_revision']='stale'
  with self.assertRaises(aw.Conflict):workspace.command(body,7,self.root,self.path)
 def test_numeric_and_tube_characteristic_conflicts(self):
  from product_matching import compare
  self.assertTrue(compare('Труба PPR Ø50 PN25','Труба PP-R Дн25 Ру25')['conflicts'])
  self.assertTrue(compare('Отвод PPR 90° Ø50','Угольник PP-R Дн50х45гр')['conflicts'])

 def test_split_same_supplier_line_across_two_positions_of_one_deal(self):
  key,data=self.imported();rows=[{**self.rows[0],'offer_row_id':'a','qty':7},{**self.rows[0],'offer_row_id':'b','qty':7}]
  stock=data['unallocated_stock'][0];body={'document_key':key,'source_revision':aw.fingerprint(aw.source_document(data,key)),'allocations':[{'line_id':stock['id'],'deal_id':'1','offer_row_id':r,'qty':7,'covered_qty':7,'identity_confirmed':True,'reason':'Две позиции одного договора'} for r in ('a','b')]}
  plan=apply.prepare(body,self.deals,data,lambda _:rows);self.assertEqual([x['amount_cents'] for x in plan['targets']],[5000,5000]);self.assertEqual({x['offer_row_id'] for x in plan['targets']},{'a','b'})
 def test_review_and_superseded_invoices_cannot_allocate(self):
  key,data=self.imported()
  for state in ('review','version_review','superseded','processing','error'):
   data['invoices'][0]['intake']['state']=state;self.assertFalse(aw.public_document(aw.source_document(data,key),{})['editable'])
 def test_alternate_version_retry_does_not_bypass_review(self):
  key,data=self.imported();data['invoices'][0]['intake']['state']='version_review';self.path.write_text(json.dumps(data))
  with self.assertRaisesRegex(ValueError,'версию'):workspace.command({'document_key':key,'action':'retry'},7,self.root,self.path)
 def test_spreadsheet_decimal_format_grounding(self):
  parsed=copy.deepcopy(self.parsed);intake.validate(parsed,{},'Труба | 14.0 | 100.0 | шт')
  with self.assertRaisesRegex(ValueError,'не найдена'):intake.validate(parsed,{},'Труба | 14.0 | 100.01 | шт')
 def test_repair_historical_lump_sum_preserves_cost(self):
  key,data=self.imported();inv=data['invoices'][0];inv['allocations']=[{'deal_id':'1','amount':50}];inv['intake']['state']='review';data['unallocated_stock']=[];self.path.write_text(json.dumps(data))
  result=intake.repair_usage(key,{'allocation:0':[{'line_no':1,'qty':7,'amount_cents':5000}]},self.path)
  self.assertEqual(result['state'],'ready');after=json.loads(self.path.read_text());self.assertEqual(after['invoices'][0]['allocations'][0]['amount'],50);self.assertEqual(after['unallocated_stock'][0]['available_qty'],7);self.assertEqual(self.loader('1'),self.rows)
 def test_stock_budget_shared_across_candidates(self):
  document={'lines':[{'id':'a','qty':5},{'id':'b','qty':5}]};opts=[{'line_id':sid,'approved':True,'unit_compatible':True,'deal_id':'1','offer_row_id':'r','remaining':7,'id':sid,'reason':'exact'} for sid in ('a','b')]
  parts=matching.auto_parts(document,opts);self.assertEqual([p['qty'] for p in parts],['5','2'])

 def test_source_number_must_match_even_with_same_supplier_and_total(self):
  with self.assertRaisesRegex(ValueError,'Номер счёта'):intake.validate(copy.deepcopy(self.parsed),{'number':'S2'},'Счёт S1 | 100.00')
 def test_russian_decimal_quantity_is_supported(self):
  p=copy.deepcopy(self.parsed);p['lines'][0]['qty']='1 000,5';intake.validate(p,{});self.assertEqual(p['lines'][0]['qty'],'1000.5')

 def test_changed_article_cannot_duplicate_old_stock_during_reparse(self):
  key,data=self.imported();parsed=copy.deepcopy(self.parsed);parsed['lines'][0]['sku']='new-article'
  result=intake.install(key,parsed,self.path);self.assertEqual(result['state'],'review');self.assertEqual(len(json.loads(self.path.read_text())['unallocated_stock']),1)
  stock=data['unallocated_stock'][0];result=intake.repair_usage(key,{'stock:'+stock['id']:1},self.path)
  self.assertEqual(result['state'],'ready');after=json.loads(self.path.read_text());self.assertEqual(len(after['unallocated_stock']),1);self.assertEqual(after['unallocated_stock'][0]['sku'],'new-article');self.assertEqual(after['unallocated_stock'][0]['available_amount'],100)

 def test_derived_invoice_totals_do_not_invalidate_other_pending_allocation(self):
  key,data=self.imported();first=aw.fingerprint(aw.source_document(data,key));data['invoices'][0].update(allocated_total=0,status='открыт',unallocated_total=100,stock_allocated_total=0)
  self.assertEqual(first,aw.fingerprint(aw.source_document(data,key)))
  data['unallocated_stock'][0]['available_qty']=13;self.assertNotEqual(first,aw.fingerprint(aw.source_document(data,key)))

 def test_combined_bank_payment_uses_confirmed_invoice_split(self):
  (self.root/'evidence/posting').mkdir(parents=True);(self.root/'reports').mkdir();crm=self.root/'crm';crm.mkdir()
  source1=self.root/'one.pdf';source1.write_text('one');source2=self.root/'two.pdf';source2.write_text('two')
  catalog=[{'source':str(p),'number':n,'supplier_inn':'123','amount_cents':c} for p,n,c in [(source1,'1280',1800000),(source2,'1299',5976000)]]
  (self.root/'evidence/posting/archive_catalog.json').write_text(json.dumps(catalog))
  row={'id':'a'*64,'direction':'out','inn':'123','document_numbers':'1280','amount_cents':7776000,'date':'2026-05-22','confirmed_payment_allocations':[{'deal_id':'856','invoice_number':'1280','amount_cents':1800000},{'deal_id':'854','invoice_number':'1299','amount_cents':5976000}]}
  (self.root/'reports/ledger.json').write_text(json.dumps([row]));docs={x['number']:x for x in intake.discover(self.root,crm)}
  self.assertEqual(docs['1280']['payments'][0]['amount'],18000);self.assertEqual(docs['1299']['payments'][0]['amount'],59760);self.assertEqual(docs['1280']['deal_ids'],['856']);self.assertEqual(docs['1299']['deal_ids'],['854'])
