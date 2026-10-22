import copy,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import shipment_workspace as s
class ShipmentWorkspaceTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.db=Path(self.tmp.name)/'ship.sqlite3';self.p=patch.object(s,'DB',self.db);self.p.start()
  self.data={'contract_date_iso':'2026-09-01','total':'100.00','positions':[{'id':'1','name':'Товар <img>','kind':'goods','unit':'шт.','quantity':'3','total':'100.00','unit_price':'33.33','tax_rate':5}]}
  self.saved=s.save_book('1',self.data)
 def tearDown(self):self.p.stop();self.tmp.cleanup()
 def body(self,q='1',key='request-00000001'):
  return {'deal_id':'1','request_id':key,'fingerprint':self.saved['fingerprint'],'transfer_date':'2026-09-30','positions':[{'id':'1','quantity':q}]}
 def test_rounding_last_part_and_exact_totals(self):
  totals=[]
  for i in range(3):
   s.confirm(self.body(key='request-0000000'+str(i)),77);totals.append(s.shipments('1')[-1]['payload']['total'])
  self.assertEqual(totals,['33.33','33.34','33.33']);self.assertTrue(s.complete_volume('1'))
  with self.assertRaisesRegex(ValueError,'остаток'):s.confirm(self.body(key='request-00000009'),77)
 def test_repeated_confirmation_and_changed_replay(self):
  body=self.body();a=s.confirm(body,77);self.assertEqual(s.confirm(body,77),a);self.assertEqual(len(s.shipments('1')),1)
  body['positions'][0]['quantity']='2'
  with self.assertRaises(ValueError):s.confirm(body,77)
 def test_stale_snapshot_unknown_and_duplicate_lines_rejected(self):
  b=self.body();b['fingerprint']='old'
  with self.assertRaises(ValueError):s.confirm(b,77)
  b=self.body();b['positions']*=2
  with self.assertRaises(ValueError):s.confirm(b,77)
  b=self.body();b['positions'][0]['id']='foreign'
  with self.assertRaises(ValueError):s.confirm(b,77)
 def test_nonfinite_negative_fractional_goods_rejected(self):
  for v in ('NaN','Infinity','-1','0','0.5','4'):
   with self.subTest(v=v),self.assertRaises(ValueError):s.confirm(self.body(q=v),77)
 def test_named_work_stage_requires_basis_and_cost_conservation(self):
  self.data['positions'][0].update(kind='work',unit='компл.',quantity='1');self.saved=s.save_book('1',self.data)
  b=self.body('0.5')
  with self.assertRaises(ValueError):s.confirm(b,77)
  b['positions'][0].update(stage='Монтаж',stage_basis='Спецификация этапов 1',stage_amount='60.00');s.confirm(b,77)
  b=self.body('0.5','request-00000002');b['positions'][0].update(stage='Пусконаладка',stage_basis='Спецификация этапов 1',stage_amount='50.00')
  with self.assertRaises(ValueError):s.confirm(b,77)
  b['positions'][0]['stage_amount']='40.00';s.confirm(b,77);self.assertTrue(s.complete_volume('1'))
 def test_amount_only_work_and_exact_last_remainder(self):
  self.data['total']='709686.00';self.data['positions'][0].update(kind='work',quantity='1',total='709686.00',unit_price='709686.00');self.saved=s.save_book('1',self.data)
  b=self.body();b['positions']=[{'id':'1','amount_mode':True,'stage_amount':'407186'}]
  result=s.preview(b);self.assertEqual(result['total'],'407186');self.assertEqual(result['positions'][0]['quantity'],'1');self.assertEqual(result['positions'][0]['unit'],'этап')
  first=s.confirm(b,77);self.assertEqual(s.confirm(b,77),first)
  self.assertEqual(s.projection('1')['book']['data']['positions'][0]['remaining_total'],'302500.00')
  b=self.body(key='request-00000002');b['positions']=[{'id':'1','amount_mode':True,'stage_amount':'302500.01'}]
  with self.assertRaises(ValueError):s.confirm(b,77)
  b['positions'][0]['stage_amount']='302500';s.confirm(b,77);self.assertTrue(s.complete_volume('1'))
 def test_three_work_transfers_keep_contract_name_and_total(self):
  self.data['positions'][0].update(name='Монтажные работы',kind='work',quantity='1',total='709686.00');self.saved=s.save_book('1',self.data)
  for i,amount in enumerate(['407186','100000','202500']):
   b=self.body(key='three-parts-0000'+str(i));b['positions']=[{'id':'1','amount_mode':True,'stage_amount':amount}]
   result=s.preview(b);self.assertEqual(result['positions'][0]['name'],'Монтажные работы')
   bad=copy.deepcopy(b);bad['positions'][0]['stage_amount']=str(s.decimal(amount)+s.decimal('709686'))
   with self.assertRaises(ValueError):s.confirm(bad,77)
   receipt=s.confirm(b,77);self.assertEqual(s.confirm(b,77),receipt)
  self.assertTrue(s.complete_volume('1'));self.assertEqual(len(s.shipments('1')),3)
  self.assertEqual(sum(s.decimal(x['payload']['total']) for x in s.shipments('1')),s.decimal('709686'))
  with self.assertRaises(ValueError):s.confirm(self.body(key='fourth-part-00000'),77)
 def test_amount_mode_cannot_split_goods(self):
  b=self.body();b['positions'][0].update(amount_mode=True,stage='Этап',stage_amount='10')
  with self.assertRaises(ValueError):s.confirm(b,77)
 def test_preview_has_no_write_and_payment_needs_basis(self):
  b=self.body();v=s.preview(b);self.assertEqual(v['total'],'33.33');self.assertFalse(s.shipments('1'))
  b['payment']={'amount':'1'}
  self.assertTrue(s.preview(b)['blocking_errors']);self.assertIn('очистите',s.preview(b)['blocking_errors'][0]);self.assertFalse(s.shipments('1'))
  with self.assertRaises(ValueError):s.confirm(b,77)
 def test_payment_preview_and_confirm_agree(self):
  for payment in ({'amount':'34','basis':'Этап','clause':'6.4.2'}, {'amount':'NaN','basis':'Этап','clause':'6.4.2'}, {'amount':'1','basis':'Этап','clause':''}):
   b=self.body();b['payment']=payment
   self.assertTrue(s.preview(b)['blocking_errors'])
   with self.assertRaises(ValueError):s.confirm(b,77)
  b=self.body();b['payment']={'amount':'1','basis':'Этап','clause':'6.4.2'}
  self.assertFalse(s.preview(b)['blocking_errors']);s.confirm(b,77)
 def test_confirmed_volume_is_reserved_even_during_delivery_failure(self):
  a=s.confirm(self.body('3'),77);s.patch(a['id'],state='ready',values={'error':'Email timeout'})
  self.assertEqual(s.projection('1')['book']['data']['positions'][0]['remaining_quantity'],'0')
  with self.assertRaises(ValueError):s.confirm(self.body(key='request-00000002'),77)
 def test_bad_date_rejected(self):
  b=self.body();b['transfer_date']='9999-01-01'
  with self.assertRaises(ValueError):s.confirm(b,77)
 def test_read_projection_does_not_modify_source_fingerprint(self):
  before=s.book('1')['data'];s.projection('1');self.assertEqual(s.book('1')['data'],before)
if __name__=='__main__':unittest.main()

class ShipmentReleaseGuardTests(unittest.TestCase):
 setUp=ShipmentWorkspaceTests.setUp
 tearDown=ShipmentWorkspaceTests.tearDown
 body=ShipmentWorkspaceTests.body
 def test_contract_mismatch_keeps_preview_rows_but_blocks_financial_confirmation(self):
  self.data['blocking_errors']=['Договор 110 ₽; сделка 100 ₽'];self.saved=s.save_book('1',self.data)
  b=self.body();result=s.preview(b);self.assertEqual(len(result['positions']),1);self.assertTrue(result['blocking_errors'])
  with self.assertRaisesRegex(ValueError,'Договор'):s.confirm(b,77)
  self.assertFalse(s.shipments('1'))
 def test_tax_policy_is_checked_for_selected_date_before_reserving_volume(self):
  self.data['tax_policy']=[{'from':'2026-01-01','rate':-1},{'from':'2026-10-01','rate':5}];self.data['positions'][0]['tax_rate']=-1;self.saved=s.save_book('1',self.data)
  b=self.body();b['transfer_date']='2026-10-13';self.assertIn('НДС 5%',s.preview(b)['blocking_errors'][0])
  with self.assertRaises(ValueError):s.confirm(b,77)
  b['transfer_date']='2026-09-30';s.confirm(b,77)

class CardProgressTests(unittest.TestCase):
 def test_confirmed_partial_cancelled_and_missing_total(self):
  with tempfile.TemporaryDirectory() as tmp:
   db=Path(tmp)/'db.sqlite3'
   with s.connection(db) as conn:
    for ident,state,amount in [('a','confirmed','25'),('b','error','25'),('c','cancelled','99'),('d','legacy_full','50')]:
     conn.execute('INSERT INTO shipments VALUES(?,?,?,?,?,?)',(ident,'1',ord(ident),state,__import__('json').dumps({'total':amount}),0))
   cards=[{'id':'1','total':20000},{'id':'2','total':10000},{'id':'3','total':0},{'id':'4','total':None}]
   result=s.card_progress(cards,db)
   self.assertEqual(result[0]['shipment_progress'],{'known':True,'amount_cents':10000,'percent':50.0})
   self.assertEqual(result[1]['shipment_progress']['percent'],0)
   self.assertIsNone(result[2]['shipment_progress']['percent']);self.assertIsNone(result[3]['shipment_progress']['percent'])
   self.assertNotIn('shipment_progress',cards[0])
   cards[0]['total']=10000;self.assertEqual(s.card_progress(cards,db)[0]['shipment_progress']['percent'],100)
   cards[0]['total']=5000;self.assertEqual(s.card_progress(cards,db)[0]['shipment_progress']['percent'],200)
 def test_missing_registry_is_unknown_not_zero(self):
  with tempfile.TemporaryDirectory() as tmp:
   db=Path(tmp)/'missing.db'
   self.assertEqual(s.card_progress([{'id':'1','total':10000}],db)[0]['shipment_progress'],{'known':False,'amount_cents':None,'percent':None})
   self.assertFalse(db.exists())
