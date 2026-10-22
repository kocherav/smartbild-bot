import unittest

import build_profitability_report as report


class ProfitabilityPlanFactTest(unittest.TestCase):
    def test_confirmed_profit_field_is_not_rewritten_after_unknown_response(self):
        self.assertTrue(report.money_field_matches(
            {"valueInMain": 1495567.972381, "value": 1495567.9724},
            1495567.972380953,
        ))
        self.assertFalse(report.money_field_matches({"value": 10}, 11))

    def test_extra_cost_does_not_close_same_named_work(self):
        entries=[{'offer_row_id':'1','name':'Доставка','qty':1,'sell_price':5000,'cost_work':1000}]
        installation={'work:1':{'cost_kind':'extra_work','name':'Доставка','planned_qty':0,'rate':0,'accepted_qty':0,'accepted_amount':4000}}
        rows,_,cost,_,_=report.compute_profitability(entries,{},installation)
        self.assertEqual(5000,cost);self.assertEqual(0,rows[0]['fact_work'])
        self.assertEqual(4000,rows[-1]['fact_work']);self.assertEqual(0,rows[-1]['fact_work_qty'])
    def test_installer_material_is_not_labour_or_duplicate_name_mapping(self):
        entries=[{'offer_row_id':'1','name':'Cable','qty':1,'sell_price':1000,'cost_work':0}]
        installation={'work:1':{'cost_kind':'material','name':'Cable','planned_qty':1,'rate':100,'accepted_qty':1,'accepted_amount':100}}
        rows,_,cost,_,_=report.compute_profitability(entries,{},installation)
        self.assertEqual(100,cost)
        self.assertEqual(0,sum(r['fact_work'] for r in rows))
        self.assertEqual(100,sum(r['fact_material'] for r in rows))
    def test_same_named_positions_use_distinct_work_ids(self):
        entries=[{'offer_row_id':'1','name':'Cable','qty':1,'sell_price':1000},
                 {'offer_row_id':'2','name':'Cable','qty':1,'sell_price':1000}]
        installation={'row:1':{'name':'Cable','planned_qty':1,'rate':100,'accepted_qty':1,'accepted_amount':100},
                      'row:2':{'name':'Cable','planned_qty':1,'rate':200,'accepted_qty':1,'accepted_amount':200}}
        rows,_,cost,_,_=report.compute_profitability(entries,{},installation)
        self.assertEqual(300,cost)
        self.assertEqual([100,200],[x['fact_work'] for x in rows])

    def test_ambiguous_name_only_mapping_is_rejected(self):
        entries=[{'offer_row_id':'1','name':'Cable','qty':1,'sell_price':1000},
                 {'offer_row_id':'2','name':'Cable','qty':1,'sell_price':1000}]
        with self.assertRaisesRegex(ValueError,'Неоднозначная'):
            report.compute_profitability(entries,{}, {'cable':{'planned_qty':1,'rate':100}})

    def test_manual_work_is_not_lost_without_commercial_position(self):
        rows,_,cost,_,_=report.compute_profitability([],{}, {'work:5':{'name':'Extra','planned_qty':2,'rate':100,'accepted_qty':1,'accepted_amount':80}})
        self.assertEqual(180,cost); self.assertEqual(80,rows[0]['fact_work'])

    def test_explicit_zero_accepted_amount_is_not_recalculated(self):
        rows,_,_,_,_=report.compute_profitability([{'name':'Cable','qty':1,'sell_price':1000}],{},
            {'cable':{'planned_qty':1,'rate':100,'accepted_qty':1,'accepted_amount':0}})
        self.assertEqual(0,rows[0]['fact_work'])

    def test_fact_and_remaining_plan_form_forecast(self):
        entries = [{"offer_row_id": "10", "name": "Кабель", "qty": 10,
                    "sell_price": 200, "cost_material": 130, "cost_work": 5}]
        procurement = {"10": {"planned_unit_cost": 100, "planned_unit_work": 5,
                               "actual_qty": 4, "actual_total": 520}}
        rows, revenue, cost, profit, margin = report.compute_profitability(entries, procurement)
        row = rows[0]
        self.assertEqual(1000, row["plan_material"])
        self.assertEqual(520, row["fact_material"])
        self.assertEqual(600, row["remaining_plan_material"])
        self.assertEqual(1170, row["forecast_cost"])
        self.assertEqual(2000, revenue)
        self.assertEqual(1170, cost)
        self.assertEqual(830, profit)
        self.assertAlmostEqual(41.5, margin)

    def test_additional_expense_reduces_profit_without_sale_position(self):
        entries = [{"offer_row_id": "10", "name": "Кабель", "qty": 1,
                    "sell_price": 1000, "cost_material": 500, "cost_work": 0}]
        procurement = {"10": {"planned_unit_cost": 500},
                       "__additional_expenses__": [{"source_name": "Расходные материалы", "amount": 120}]}
        rows, revenue, cost, profit, _ = report.compute_profitability(entries, procurement)
        self.assertEqual(2, len(rows))
        self.assertEqual(620, cost)
        self.assertEqual(380, profit)
        self.assertEqual(-120, rows[-1]["profit"])

    def test_currency_invoice_is_plan_until_bank_payment_then_uses_payment_fact(self):
        entries = [{"offer_row_id": "10", "name": "Блок", "qty": 2,
                    "sell_price": 100000, "cost_material": 40000, "cost_work": 0}]
        # One line is covered by a EUR invoice.  103k is its plan based on CBR+
        # markup; after a 105k bank debit the complete actual payment is fact.
        procurement = {"10": {"planned_unit_cost": 40000, "invoiced_qty": 1,
                               "invoice_plan_total": 103000, "paid_invoice_qty": 1,
                               "paid_invoice_total": 105000}}
        rows, _, cost, _, _ = report.compute_profitability(entries, procurement)
        row = rows[0]
        self.assertEqual(143000, row["plan_material"])
        self.assertEqual(105000, row["fact_material"])
        self.assertEqual(40000, row["remaining_plan_material"])
        self.assertEqual(145000, cost)

    def test_line_total_is_never_multiplied_again_when_report_qty_differs(self):
        entries = [{"offer_row_id": "x", "name": "Трасса", "qty": 158,
                    "sell_price": 2800, "cost_material": 135000, "cost_work": 0}]
        procurement = {"x": {"planned_unit_cost": 135000 / 158,
                              "planned_total": 135000,
                              "planned_material_basis": "line_total"}}
        installation = {report.norm("Трасса"): {"planned_qty": 80, "rate": 0, "accepted_qty": 0}}
        rows, _, cost, _, _ = report.compute_profitability(entries, procurement, installation)
        self.assertEqual(135000, rows[0]["plan_material"])
        self.assertEqual(135000, rows[0]["remaining_plan_material"])
        self.assertEqual(135000, cost)

    def test_installer_report_changes_work_scope_not_commercial_quantity(self):
        entries=[{"offer_row_id":"10","name":"Монтаж трассы","qty":158,
                  "sell_price":2800,"cost_material":100,"cost_work":120000}]
        installation={report.norm("Монтаж трассы"):{"planned_qty":80,"rate":1500,"accepted_qty":40}}
        rows,revenue,cost,_,_=report.compute_profitability(entries,{},installation)
        row=rows[0]
        self.assertEqual(158,row['qty'])
        self.assertEqual(60000,row['fact_work'])
        self.assertEqual(60000,row['remaining_plan_work'])
        self.assertEqual(135800,cost)
        self.assertEqual(442400,revenue)

    def test_aggregate_montage_line_does_not_duplicate_itemized_labour(self):
        entries = [
            {"offer_row_id": "1", "name": "Прокладка кабеля", "qty": 10,
             "sell_price": 200, "cost_material": 20, "cost_work": 30},
            {"offer_row_id": "2", "name": "Монтажные работы", "qty": 1,
             "sell_price": 1000, "cost_material": 300, "cost_work": 0},
        ]
        rows, revenue, cost, profit, _ = report.compute_profitability(entries)
        montage = next(x for x in rows if x["name"] == "Монтажные работы")
        self.assertEqual(0, montage["forecast_cost"])
        self.assertEqual(500, cost)
        self.assertEqual(3000, revenue)
        self.assertEqual(2500, profit)


if __name__ == "__main__":
    unittest.main()
