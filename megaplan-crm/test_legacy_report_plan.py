import unittest
from copy import deepcopy
from legacy_report_plan import plan

class LegacyPlanTests(unittest.TestCase):
    def setUp(self):
        self.works={'861':[{'id':3,'name':'Монтаж кабеля','unit':'м','planned_qty':100,'accepted_qty':40,'rate':10}]}
        self.session={'exceptions':[{'id':1,'type':'table','deal_id':'861','source':'Выполнение по таблице','table_rows':[
            {'name':'Монтаж кабеля','unit':'м','current_qty':20,'current_amount':200,'cumulative_qty':60}]}],
            'report_lines':[{'deal_id':'861','source':'Выполнение по таблице','kind':'Работа по таблице','amount':200}]}
    def test_only_current_delta_and_no_aggregate_double_count(self):
        result=plan(self.session,self.works)
        self.assertTrue(result['ready']); self.assertEqual('200',result['total'])
        self.assertEqual('20',result['matched'][0]['quantity'])
        self.assertEqual(1,len(result['matched']))
    def test_resolved_aggregate_annotation_does_not_repeat_table_work(self):
        self.session['exceptions'].append({'type':'deal','deal_id':'861','source':'Выполнение по таблице','amount':200,'qty':20,'unit':'м'})
        result=plan(self.session,self.works)
        self.assertTrue(result['ready']);self.assertEqual('200',result['total']);self.assertEqual(1,len(result['matched']))
    def test_extra_cost_retains_amount_and_does_not_require_quantity(self):
        self.session={'report_lines':[{'deal_id':'861','source':'Доставка','amount':4000,'extra_cost_confirmed':True}]}
        result=plan(self.session,self.works)
        self.assertTrue(result['ready']);self.assertEqual([],result['matched'])
        self.assertEqual('4000',result['additional_costs'][0]['amount'])
    def test_ambiguous_position_requires_mapping(self):
        self.works['861'].append({**self.works['861'][0],'id':4})
        self.assertFalse(plan(self.session,self.works)['ready'])
        self.session['exceptions'][0]['table_rows'][0]['work_item_id']=3
        self.assertTrue(plan(self.session,self.works)['ready'])
    def test_mismatched_unit_or_rate_is_not_guessed(self):
        for field,value in [('unit','шт.'),('rate',20)]:
            works=deepcopy(self.works); works['861'][0][field]=value
            self.assertFalse(plan(self.session,works)['ready'])
    def test_repeated_rows_cannot_exceed_remaining(self):
        row=self.session['exceptions'][0]['table_rows'][0]
        self.session['exceptions'][0]['table_rows']=[deepcopy(row) for _ in range(4)]
        result=plan(self.session,self.works)
        self.assertFalse(result['ready']); self.assertEqual(1,len(result['review']))
    def test_payment_is_not_accepted_as_work(self):
        self.session['report_lines'].append({'deal_id':'861','kind':'Аванс','amount':100,'sign':-1})
        result=plan(self.session,self.works)
        self.assertEqual('200',result['total']); self.assertEqual(1,len(result['separate_settlements']))
    def test_material_cannot_close_work_even_with_same_name_unit_and_rate(self):
        self.session['report_lines'].append({'deal_id':'861','source':'Монтаж кабеля','unit':'м','qty':1,'amount':10,'kind':'Материал'})
        result=plan(self.session,self.works)
        self.assertFalse(result['ready']); self.assertEqual('200',result['total'])
        self.assertEqual(1,len(result['cost_review']))
    def test_manager_exception_without_quantity_is_not_silently_dropped(self):
        self.session['exceptions'].append({'type':'amount','deal_id':'861','source':'Дополнительные работы','amount':300,'resolution':'на сделку'})
        result=plan(self.session,self.works)
        self.assertFalse(result['ready']); self.assertEqual(1,len(result['review']))
    def test_material_exception_does_not_reappear_as_work_after_cost_confirmation(self):
        self.session['report_lines'].append({'kind':'Материал','deal_id':'861','source':'Материал-8.000','amount':8000,'cost_decision':'additional','cost_confirmed':True})
        self.session['exceptions'].append({'type':'material','deal_id':'861','source':'Материал-8.000','amount':8000,'resolution':'внеплановый расход'})
        result=plan(self.session,self.works)
        self.assertTrue(result['ready']);self.assertEqual([],result['review'])
        self.assertEqual(1,len(result['materials']));self.assertEqual('200',result['total'])
        self.session['report_lines'][-1].pop('cost_confirmed')
        result=plan(self.session,self.works)
        self.assertEqual(1,len(result['cost_review']));self.assertEqual([],result['review'])
    def test_explicit_miscellaneous_stays_separate(self):
        self.session['exceptions'].append({'type':'amount','deal_id':'861','source':'Дополнительные работы','amount':300,'bucket':'Всякая всячина'})
        result=plan(self.session,self.works)
        self.assertEqual('200',result['total']); self.assertEqual(1,len(result['separate_settlements']))
    def test_only_explicit_miscellaneous_can_be_reviewed_without_fake_work(self):
        result=plan({'exceptions':[{'type':'amount','source':'Прочий расход','amount':300,'bucket':'Всякая всячина'}]}, {})
        self.assertTrue(result['ready']);self.assertEqual([],result['matched']);self.assertEqual('0',result['total'])
        self.assertFalse(plan({'report_lines':[{'source':'неразобранная строка','amount':300}]},{})['ready'])
    def test_no_input_mutation_and_fingerprint_tracks_work_changes(self):
        before=deepcopy(self.session); key=plan(self.session,self.works)['fingerprint']
        self.assertEqual(before,self.session)
        self.works['861'][0]['accepted_qty']=50
        self.assertNotEqual(key,plan(self.session,self.works)['fingerprint'])

if __name__=='__main__': unittest.main()
