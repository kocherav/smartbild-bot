import copy,unittest
from position_types import classify_position,name_kind,new_offer_type,resolve,FIELD,GOODS,WORK
from generate_contract import contract_data
from position_type_migration import plan,apply
from megaplan_api import MegaplanAPI
from unittest.mock import Mock

class PositionTypeSourceTests(unittest.TestCase):
 def test_real_861_goods_mixed_costs(self):
  names=['Монтажная плата частичная, фронтальная для корпусов RAM fit, ВхШ 400х800 мм','Рама монтажная для корпусов RAM fit, ВхШ 2000х800 мм','DKC Кронштейны рамы монтажной платы для корпусов RAM fit','Наконечник медный луженый штифтовой НШП-50,0 под опрессовку КВТ','Наконечник медный луженый штифтовой НШП-16,0 под опрессовку КВТ']
  amounts=[7137,18117,7686,18180,5850];rows=[]
  for i,(name,amount) in enumerate(zip(names,amounts)):
   offer={'name':name,'type':'product','Category1000045CustomFieldTsenaZakupki':{'value':100},'Category1000045CustomFieldSebesRabot':{'value':700}}
   self.assertNotEqual(classify_position({'offer':offer}),'work');self.assertNotEqual(name_kind(name),'work')
   rows.append({'id':str(i),'offer':offer,'quantity':1,'sum':{'value':amount}})
  result=contract_data({'positions':rows,'price':{'value':56970}}, {})
  self.assertEqual(result['works'],0);self.assertEqual(result['advance'],56970)
  self.assertTrue(all(r['position_type']=='product' for r in result['positions']))
 def test_crm_is_authoritative_even_against_name_and_cost(self):
  self.assertEqual(classify_position({'name':'Кабель','offer':{'type':'service','Category1000045CustomFieldTsenaZakupki':{'value':100}}}),'work')
  self.assertNotEqual(classify_position({'name':'Монтаж','offer':{'type':'product',FIELD:GOODS,'Category1000045CustomFieldSebesRabot':{'value':100}}}),'work')
  with self.assertRaises(ValueError):classify_position({'name':'Монтаж','offer':{'type':'product'}})
  with self.assertRaises(ValueError):resolve({'offer':{'type':'product'}},'work')
  with self.assertRaises(ValueError):classify_position({'offer':{'type':'bad'}})
 def test_explicit_field_on_immutable_crm_clone(self):
  self.assertEqual(classify_position({'offer':{'type':'product','name':'Монтажные работы',FIELD:WORK}}),'work')
  self.assertEqual(MegaplanAPI.ledger_from_deal({'positions':[{'id':'1','quantity':1,'offer':{'type':'product','name':'Монтажные работы',FIELD:WORK}}]})[0]['position_type'],'service')
  self.assertNotEqual(classify_position({'offer':{'type':'service','name':'Монтажная плата',FIELD:GOODS}}),'work')
  self.assertEqual(classify_position({'offer':{'type':'product',FIELD:'  работы / услуги  '}}),'work')
  with self.assertRaises(ValueError):classify_position({'offer':{'type':'product',FIELD:'неизвестно'}})
 def test_types_flow_into_proposal_and_partial_contract(self):
  from deal_proposal import snapshot
  from partial_shipments import apply as partial_apply
  rows=[{'id':'1','name':'Монтажная плата','offer':{'id':'2','name':'Монтажная плата','type':'product',FIELD:GOODS},'quantity':2,'unit':{'name':'шт.'},'sum':{'value':100,'currency':'RUB'},'tax':{'rate':-1}},
        {'id':'3','name':'Монтаж платы','offer':{'id':'4','name':'Монтаж платы','type':'product',FIELD:WORK},'quantity':1,'unit':{'name':'усл.'},'sum':{'value':50,'currency':'RUB'},'tax':{'rate':-1}}]
  deal={'id':'99','positions':rows,'price':{'value':150,'currency':'RUB'},'contractor':{'name':'Тест'},'name':'Тест'}
  d=contract_data(deal,{})
  self.assertEqual([p['kind']=='work' for p in d['positions']],[False,True])
  from unittest.mock import patch
  shipment={'positions':d['positions'][:1],'total':'100','act_number':'99-АПП/01','transfer_date':'30.09.2026'}
  with patch('document_tax_policy.company_rate',return_value=-1):
   result=partial_apply({'shipment':shipment},{**d,'seller':{'id':'test'}})
  self.assertEqual(result['total'],'100');self.assertFalse(any(x['kind']=='work' for x in result['positions']))
  p=snapshot(deal)
  self.assertEqual([x['section'] for x in p['rows']],['Оборудование и материалы','Работы и логистика'])
 def test_new_actions_and_items(self):
  for name in ['Монтаж кабельного лотка','Оконцевание, опрессовка и подключение кабеля','Устройство перемычек','Испытания системы','Доставка оборудования','Монтажные работы']:
   self.assertEqual(new_offer_type(name),'service',name)
  for name in ['Монтажная коробка','Монтажные расходные материалы','Наконечник под опрессовку','Кабель для подключения','Установка приточно-вытяжная с рекуператором Zenit Heco VM 350']:
   self.assertEqual(new_offer_type(name),'product',name)
 def test_create_offer_persists_type(self):
  api=object.__new__(MegaplanAPI);api._call=Mock(side_effect=[{'data':[]},{'data':[{'id':'2','type':'service'}]},{'data':{'id':'7'}},{'data':{'id':'7',FIELD:WORK}}])
  api.find_or_create_offer('Монтаж кабеля',100)
  body=api._call.call_args_list[2].kwargs['json_body'];self.assertEqual(body['type'],'service');self.assertEqual(body[FIELD],WORK);self.assertEqual(body['category']['id'],'2')
 def test_migration_resume_no_duplicate_write(self):
  offer={'id':'2','name':'Монтаж кабеля','type':'product','price':{'value':100}}
  deal={'id':'1','positions':[{'id':'3','offer':offer}]};change=plan(deal)[0]
  writes=[]
  class API:
   def _call(self,method,path,json_body=None):
    if method=='POST':writes.append(path);offer[FIELD]=json_body[FIELD]
    return {'data':copy.deepcopy(deal if path.startswith('/deal/') else offer)}
  api=API();self.assertTrue(apply(api,change)['verified']);self.assertTrue(apply(api,change)['unchanged']);self.assertEqual(len(writes),1)
  offer['name']='Другой товар'
  with self.assertRaises(ValueError):apply(api,change)

class ExistingCatalogTypeTests(unittest.TestCase):
 def test_existing_catalog_work_persists_explicit_type_without_changing_money(self):
  from position_types import prepare_offer
  offer={'id':'7','name':'Монтаж платы','type':'product','price':{'value':100}}
  calls=[]
  class API:
   def _call(self,method,path,json_body=None):
    calls.append((method,path,json_body))
    if method=='POST':offer.update(json_body)
    return {'data':copy.deepcopy(offer)}
  self.assertEqual(prepare_offer(API(),'7'),'service')
  self.assertEqual(offer[FIELD],WORK);self.assertEqual(offer['price']['value'],100)
  self.assertEqual(set(calls[1][2]),{'contentType',FIELD})
 def test_new_deal_uses_prepared_catalog_types(self):
  api=object.__new__(MegaplanAPI)
  offer={'id':'7','name':'Монтаж платы','type':'product',FIELD:WORK}
  api._call=Mock(side_effect=[{'data':offer},{'data':{'id':'9'}}])
  self.assertEqual(api.create_deal_with_positions('1','company',[{'offer_id':'7','qty':1,'unit_price':100}])['id'],'9')
  self.assertEqual(api._call.call_args_list[0].args,('GET','/offer/7'))
