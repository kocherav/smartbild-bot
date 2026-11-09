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


class FakeBox:
    """IMAP mailbox double: letters by UID, counts what is downloaded."""
    def __init__(self, letters, validity=b'1'):
        self.letters = letters; self.validity = validity
        self.full_fetches = 0; self.header_fetches = 0; self.logged_out = False
    def select(self, *a, **k): return 'OK', [b'1']
    def response(self, name): return name, [self.validity]
    def uid(self, command, *args):
        if command == 'SEARCH':
            return 'OK', [b' '.join(str(u).encode() for u in sorted(self.letters))]
        uid, what = args[0], args[1]
        subject, body, mid = self.letters[int(uid)]
        from email.header import Header
        subject = Header(subject, 'utf-8').encode()   # real headers are RFC 2047 encoded
        if 'HEADER.FIELDS' in what:
            self.header_fetches += 1
            raw = f'Subject: {subject}\r\nMessage-ID: {mid}\r\n\r\n'.encode()
        else:
            self.full_fetches += 1
            raw = (f'Subject: {subject}\r\nMessage-ID: {mid}\r\nContent-Type: text/plain; charset=utf-8\r\n\r\n'
                   + body).encode('utf-8')
        return 'OK', [(b'1 (BODY[] {1}', raw)]
    def logout(self): self.logged_out = True


def letter(n, body=SAMPLE):
    return ('Уведомление о платеже', body.replace('№140', f'№{n}'), f'<m{n}@alfa>')


class IncrementalPollTests(unittest.TestCase):
    def setUp(self):
        import tempfile, os, email_payment_monitor as m
        self.m = m
        self.dir = tempfile.mkdtemp()
        self.registry = os.path.join(self.dir, 'registry.json')
        self.patches = [patch.object(m, 'REGISTRY', self.registry),
                        patch.object(m, 'match_invoices', return_value={'exact': False, 'missing': [], 'matched_total': 0,
                                                                        'deal_ids': [], 'invoices': []})]
        for p in self.patches: p.start()
        self.addCleanup(lambda: [p.stop() for p in self.patches])

    def test_known_letters_are_not_downloaded_again(self):
        box = FakeBox({n: letter(n) for n in range(1, 151)})
        first = self.m.poll(connect=lambda: box)
        self.assertEqual(150, len(first['created']))
        box.letters[151] = letter(151); box.full_fetches = 0; box.header_fetches = 0
        second = self.m.poll(connect=lambda: box)
        self.assertEqual(['151'], [c['payment_number'] for c in second['created']])
        self.assertEqual(1, box.full_fetches, 'только новое письмо скачано целиком')
        self.assertEqual(1, box.header_fetches)

    def test_slow_mailbox_saves_progress_and_continues(self):
        box = FakeBox({n: letter(n) for n in range(1, 11)})
        ticks = iter(range(0, 10_000, 10))   # every check «takes» 10 seconds
        first = self.m.poll(connect=lambda: box, clock=lambda: next(ticks))
        self.assertTrue(first['more']); self.assertGreater(len(first['created']), 0)
        rest = self.m.poll(connect=lambda: box)
        self.assertEqual(10, len(first['created']) + len(rest['created']), 'ни одно письмо не потеряно и не задвоено')

    def test_unrecognised_letter_is_reported_not_silently_skipped(self):
        box = FakeBox({1: ('Уведомление о платеже', 'Новый формат письма банка без привычных полей', '<x@alfa>')})
        result = self.m.poll(connect=lambda: box)
        self.assertEqual([], result['created'])
        self.assertEqual(1, len(result['failed']))
        self.assertIn('Альфа-Банка', result['failed'][0]['error'])

    def test_other_letters_of_the_sender_are_not_downloaded(self):
        box = FakeBox({1: ('Выписка по счёту', 'реклама', '<a@alfa>'), 2: letter(2)})
        result = self.m.poll(connect=lambda: box)
        self.assertEqual(1, len(result['created'])); self.assertEqual(1, box.full_fetches)

    def test_crash_in_the_middle_keeps_what_was_done(self):
        box = FakeBox({n: letter(n) for n in range(1, 6)})
        real = box.uid
        def broken(command, *args):
            if command == 'FETCH' and args[0] == '4' and 'HEADER' not in args[1]:
                raise OSError('connection reset')
            return real(command, *args)
        box.uid = broken
        with self.assertRaises(OSError):
            self.m.poll(connect=lambda: box)
        box.uid = real
        result = self.m.poll(connect=lambda: box)
        self.assertEqual(['4', '5'], [c['payment_number'] for c in result['created']], 'продолжение с места сбоя')
