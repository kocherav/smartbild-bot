import unittest
from unittest.mock import patch
import generate_kp as g
class MultisplitTests(unittest.TestCase):
 def products(self):
  return {s:{'article':s,'defaultPrice':10000,'contractPrice':6000,'section':{'name':section},'features':[{'name':'холодопроизводительность, кВт','value':cap}],'stocks':[]} for s,section,cap in [('OUT','Мульти-сплит наружные блоки','от3.2до11'),('IN35','Мульти-сплит внутренние блоки','от1до4'),('IN25','Мульти-сплит внутренние блоки','от0.8до3.2'),('SPLIT','Сплит-системы бытовые','3.2')]}
 def render(self,items,install=True):
  p=self.products()
  with patch.object(g,'live_lookup',side_effect=lambda sku:p[sku]),patch.object(g,'get_features',side_effect=lambda x:x['features']),patch.object(g,'hogart_image_url',return_value=None),patch.object(g,'download_image',return_value=None):return g.render_variant(items,0,install)
 def test_exact_failed_configuration_three_connections_fifteen_meters(self):
  items=[{'sku':'OUT','qty':1,'line_length_m':15},{'sku':'IN35','qty':1},{'sku':'IN25','qty':2}];r=self.render(items);s=r['summary_items'];install=[x for x in s if x['type']=='install'];lines=[x for x in s if x['type']=='freon_line']
  self.assertEqual(3,sum(x['qty'] for x in install));self.assertNotIn('OUT',[x['for_sku'] for x in install]);self.assertEqual(63000,sum(x['line_total'] for x in install));self.assertEqual(15,sum(x['length_m'] for x in lines));self.assertEqual([5,10],[x['length_m'] for x in lines]);self.assertEqual(15,items[0]['line_length_m']);self.assertTrue(all(x['allocation_note'] for x in lines));self.assertEqual(sum(x['line_total'] for x in s),r['total']);self.assertAlmostEqual(sum(x['cost_total'] for x in s),r['economics']['cost'],2)
 def test_shared_and_branch_lengths_rejected(self):
  with self.assertRaisesRegex(ValueError,'одновременно'):self.render([{'sku':'OUT','line_length_m':15},{'sku':'IN25','line_length_m':15}])
 def test_outdoor_without_indoor_cannot_invent_install_price(self):
  with self.assertRaisesRegex(ValueError,'внутренних блоков'):self.render([{'sku':'OUT'}])
 def test_equipment_only_and_ordinary_split_unchanged(self):
  r=self.render([{'sku':'OUT'}],False);self.assertEqual(1,len(r['summary_items']))
  r=self.render([{'sku':'SPLIT','qty':2,'line_length_m':15}]);self.assertEqual(2,sum(x['qty'] for x in r['summary_items'] if x['type']=='install'));self.assertEqual(15,sum(x['length_m'] for x in r['summary_items'] if x['type']=='freon_line'))
 def test_multiple_outdoor_groups_require_mapping(self):
  with self.assertRaisesRegex(ValueError,'несколько наружных'):self.render([{'sku':'OUT','qty':2},{'sku':'IN25','qty':4}])
 def test_unsupported_large_single_system_is_not_clamped(self):
  with patch.object(g,'install_price_for_capacity',side_effect=ValueError('unsupported')):
   with self.assertRaisesRegex(ValueError,'не задан тариф'):self.render([{'sku':'SPLIT'}])
