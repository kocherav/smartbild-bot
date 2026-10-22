import unittest
from unittest.mock import patch
from email_payment_monitor import parse_notification, match_invoices
from megaplan_finance import operation_form, existing_operation

SAMPLE='''Уведомление о платеже №140 25.09.2026 в адрес организации ООО "ТРИО КЛИМАТ" был отправлен платёж от Общество с ограниченной ответственностью "ИНСИС" Сумма платежа : Двести рублей (251692.37 RUR) Назначение платежа : Оплата за климатическое оборудование по счету №79566, 79567 от 22 сентября 2026 к договору №OБ/ЮР-1939. Платёж, отправленный в банк, находится во вложении.'''

class EmailPaymentTests(unittest.TestCase):
    def test_saved_queue_paginates_and_excludes_created_payments(self):
        from email_payment_monitor import list_candidates
        rows=[{'id':str(i),'status':'postponed' if i%2 else 'pending','created_at':f'{i:03}'} for i in range(13)]
        rows.append({'id':'done','status':'created','created_at':'999'})
        with patch('email_payment_monitor.load_json',return_value={'candidates':rows}):
            first=list_candidates();last=list_candidates(10)
        self.assertEqual(13,first['total']);self.assertEqual(10,len(first['candidates']))
        self.assertTrue(first['has_more']);self.assertFalse(last['has_more'])
        self.assertEqual(3,len(last['candidates']))
        self.assertEqual(13,len({x['id'] for x in first['candidates']+last['candidates']}))
    def test_same_invoice_number_of_other_supplier_or_buyer_is_not_used(self):
        payment={'invoice_numbers':['1'],'amount':100,'payer':'Общество с ограниченной ответственностью «Пример»','recipient':'ООО «Поставка»'}
        invoices=[{'id':'ok','number':'1','total':100,'supplier':'ООО Поставка','buyer_inn':'111','allocations':[{'deal_id':'demo'}]},
                  {'id':'wrong','number':'1','total':100,'supplier':'ООО Другая','buyer_inn':'111','allocations':[{'deal_id':'demo'}]},
                  {'id':'other-buyer','number':'1','total':100,'supplier':'ООО Поставка','buyer_inn':'222','allocations':[{'deal_id':'demo'}]}]
        with patch('email_payment_monitor.load_json',return_value={'invoices':invoices}), patch('own_companies.companies',return_value=[{'name':'ООО Пример','inn':'111'}]):
            result=match_invoices(payment)
        self.assertTrue(result['exact']); self.assertEqual(['ok'],[x['id'] for x in result['invoices']])

    def test_name_substring_is_not_confirmation_of_our_payer(self):
        payment={'invoice_numbers':['1'],'amount':100,'payer':'Пример Чужая Компания','recipient':'Поставка'}
        with patch('email_payment_monitor.load_json',return_value={'invoices':[]}), patch('own_companies.companies',return_value=[{'name':'ООО Пример','inn':'111','aliases':['Пример']}]):
            self.assertFalse(match_invoices(payment)['exact'])

    def test_parse_real_alfa_notification(self):
        row=parse_notification(SAMPLE)
        self.assertEqual('140',row['payment_number']); self.assertEqual(251692.37,row['amount'])
        self.assertEqual(['79566','79567'],row['invoice_numbers'])

    def test_finance_form_is_expense_purchase(self):
        candidate=parse_notification(SAMPLE)
        form=operation_form(candidate,{'number':'79566','total':167011.2,'supplier_contractor_id':'supplier-fixture'},'20')
        self.assertEqual('supplier-fixture',form['Model[Contractor]'])
        self.assertEqual('0.00',form['Model[SecondarySum][Value]'])
        self.assertEqual('expense',form['Model[Kind]']); self.assertEqual('23',form['Model[OperationType]'])
        self.assertEqual('20',form['Model[RealAccount]']); self.assertEqual('167011.20',form['Model[Sum][Value]'])

    def test_retry_finds_operation_created_before_restart(self):
        candidate=parse_notification(SAMPLE)
        found=existing_operation([{
            'Id':2954,'Kind':'expense','DocumentNumber':'140','Date':'2026-09-25 12:00:00',
            'Sum':{'Value':167011.2},'RealAccount':{'Id':20},
            'Description':'Оплата поставщику по счёту №79566. Тест',
        }],candidate,{'number':'79566','total':167011.2},'20')
        self.assertEqual(2954,found['Id'])

    def test_retry_does_not_match_other_invoice(self):
        candidate=parse_notification(SAMPLE)
        found=existing_operation([{
            'Id':2954,'Kind':'expense','DocumentNumber':'140','Date':'2026-09-25 12:00:00',
            'Sum':{'Value':167011.2},'RealAccount':{'Id':20},
            'Description':'Оплата поставщику по счёту №99999. Тест',
        }],candidate,{'number':'79566','total':167011.2},'20')
        self.assertIsNone(found)

    def test_invoice_number_prefix_is_not_a_match(self):
        candidate=parse_notification(SAMPLE)
        item={'Id':1,'Kind':'expense','DocumentNumber':'140','Date':'2026-09-25 12:00:00',
              'Sum':{'Value':100},'RealAccount':{'Id':20},'Description':'Оплата по счёту №12345.'}
        self.assertIsNone(existing_operation([item],candidate,{'number':'123','total':100},'20'))

if __name__=='__main__':unittest.main()
