import hashlib
import hmac
import json
from pathlib import Path
import tempfile
import time
import unittest
import urllib.parse
from unittest.mock import patch
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import model
import server


def m(value, currency='RUB'): return {'value': value, 'currency': currency}
def operation(ident, kind='income', amount=100, typ='31'):
    return {'contentType':'FinOperation', 'id':ident, 'type':{'id':typ}, 'kind':kind,
        'incomeSum':m(amount if kind=='income' else 999), 'expenseSum':m(amount if kind=='expense' else 999),
        'date':{'value':'2026-01-01T12:00:00+00:00'}}
def deal(ident='1', ops=None, price=1000):
    return {'contentType':'Deal', 'id':ident,'price':m(price),'result':'active','state':{'id':'1','name':'Заказ'},
        'program':{'id':'16','name':'Продажа с монтажом'},'financeOperations':ops or [],'financeOperationsCount':len(ops or []),
        'timeUpdated':{'value':'2026-10-09T00:00:00+00:00'}}
def snapshot(deals=None, invoices=None):
    return {'synced_at':'2026-10-09T00:00:00+00:00','domain':'cclimat.megaplan.ru','deals':deals or [deal()], 'invoices':invoices or []}


class ProjectionTests(unittest.TestCase):
    def test_native_invoice_bank_deduplicate_and_ignore_goods(self):
        op=operation('10');d=deal(ops=[op]);inv={'contentType':'Invoice','id':'2','deal':{'id':'1'},'financeOperations':[{'contentType':'FinOperation','id':'10'}]}
        out=model.project(snapshot([d],[inv]),registry={'operations':[{'operation_id':'10','amount':100,'deal_ids':['1']} ]})['deals'][0]
        self.assertEqual(out['received'],10000);self.assertEqual(out['outstanding'],90000);self.assertEqual(len(out['payments']),1)
    def test_refunds_and_partial_payments(self):
        ops=[operation('1',amount=300),operation('2',kind='expense',amount=50),operation('3',kind='expense',amount=90,typ='23'),operation('4',amount=10,typ='23')]
        d=model.project(snapshot([deal(ops=ops)]))['deals'][0]
        self.assertEqual((d['received'],d['spent'],d['outstanding']),(25000,8000,75000))
    def test_shared_operation_not_counted_twice(self):
        a=deal('1',[operation('1')]);b=deal('2',[operation('1')]);ds=model.project(snapshot([a,b]))['deals']
        self.assertEqual(sum(d['received'] for d in ds),0);self.assertTrue(all(d['outstanding'] is None for d in ds))
    def test_unknown_currency_and_incomplete_collection(self):
        d=deal(ops=[operation('1')]);d['price']=m(100,'USD');d['financeOperationsCount']=2
        out=model.project(snapshot([d]))['deals'][0]
        self.assertIsNone(out['total']);self.assertIsNone(out['outstanding']);self.assertFalse(out['payments_complete'])
    def test_missing_procurement_is_not_zero_progress(self):
        d=model.project(snapshot())['deals'][0];self.assertFalse(d['procurement_known']);self.assertEqual(d['items'],[])
    def test_supplier_default_status_is_not_order_evidence(self):
        proc={'deals':{'1':{'items':[{'name':'Блок','qty':2,'supplier':'hogart','status':'заказано через API','actual_qty':2,'received_qty':0}]}}}
        d=model.project(snapshot(),proc)['deals'][0]
        self.assertIsNone(d['items'][0]['ordered_qty']);self.assertEqual(d['items'][0]['invoice_qty'],2);self.assertEqual(d['items'][0]['received_qty'],0)
    def test_order_requires_confirmed_complete_or_supplementary_order(self):
        item={'name':'Блок','qty':1,'supplier':'hogart'}
        proc={'deals':{'1':{'items':[item],'hogart_order':{'state':'incomplete','hogart_order_id':1}}}}
        self.assertIsNone(model.project(snapshot(),proc)['deals'][0]['items'][0]['ordered_qty'])
        proc['deals']['1']['hogart_order']['procurement_complete_across_orders']=True
        self.assertEqual(model.project(snapshot(),proc)['deals'][0]['items'][0]['ordered_qty'],1)
    def test_overpayment_separate(self):
        d=model.project(snapshot([deal(ops=[operation('1',amount=1200)])]))['deals'][0]
        self.assertEqual(d['outstanding'],0);self.assertEqual(d['overpaid'],20000)
    def test_decimal_rounding(self):
        self.assertEqual(model.cents('10.005'),1001);self.assertIsNone(model.cents('NaN'));self.assertIsNone(model.cents(None))
    def test_shared_invoice_payment_not_proportionally_invented(self):
        proc={'invoices':[{'id':'i','deal_id':'1','total':1000,'paid_total':800,'allocations':[{'deal_id':'1','amount':400},{'deal_id':'2','amount':600}]}]}
        inv=model.project(snapshot(),proc)['deals'][0]['supplier_invoices'][0]
        self.assertEqual(inv['amount'],40000);self.assertIsNone(inv['paid'])


class AuthTests(unittest.TestCase):
    def signed(self, user=123, stamp=None):
        fields={'auth_date':str(int(time.time()) if stamp is None else stamp),'user':json.dumps({'id':user}),'query_id':'test'}
        secret=hmac.new(b'WebAppData',b'TEST_TOKEN',hashlib.sha256).digest()
        fields['hash']=hmac.new(secret,'\n'.join(f'{k}={v}' for k,v in sorted(fields.items())).encode(),hashlib.sha256).hexdigest()
        return urllib.parse.urlencode(fields)
    def test_valid(self):self.assertEqual(server.verify_telegram(self.signed(),'TEST_TOKEN',{123}),123)
    def test_invalid_signature(self):
        with self.assertRaises(ValueError):server.verify_telegram(self.signed().replace('test','tampered'),'TEST_TOKEN',{123})
    def test_other_user(self):
        with self.assertRaises(ValueError):server.verify_telegram(self.signed(456),'TEST_TOKEN',{123})
    def test_expired_and_future(self):
        for stamp in (int(time.time())-601,int(time.time())+60):
            with self.assertRaises(ValueError):server.verify_telegram(self.signed(stamp=stamp),'TEST_TOKEN',{123})
    def test_duplicate_field(self):
        with self.assertRaises(ValueError):server.verify_telegram(self.signed()+'&user=%7B%22id%22%3A123%7D','TEST_TOKEN',{123})


class TaskTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.db=patch.object(server,'DB',Path(self.tmp.name)/'test.sqlite3');self.db.start();server.initialize()
        self.snap=patch.object(server,'snapshot',return_value={'deals':[{'id':'1'},{'id':'2'}]});self.snap.start()
    def tearDown(self): self.snap.stop();self.db.stop();self.tmp.cleanup()
    def test_persistence_revision_and_stale_update(self):
        task=server.save_task({'deal_id':'1','title':'Проверить поставку','owner':'Иван','due':'2026-10-12','done':False},123)
        self.assertEqual(server.task_rows()[0]['title'],'Проверить поставку')
        updated=server.save_task({**task,'done':True},123);self.assertEqual(updated['revision'],2)
        with self.assertRaises(server.Conflict):server.save_task({**task,'done':False},123)
        with server.connect() as db:self.assertEqual(db.execute('select count(*) from audit').fetchone()[0],2)
    def test_invalid_deal_date_and_moving_task(self):
        with self.assertRaises(ValueError):server.save_task({'deal_id':'99','title':'X'},123)
        with self.assertRaises(ValueError):server.save_task({'deal_id':'1','title':'X','due':'no'},123)
        t=server.save_task({'deal_id':'1','title':'X'},123)
        with self.assertRaises(server.Conflict):server.save_task({**t,'deal_id':'2','done':False},123)
    def test_session_expiry_and_revocation(self):
        token=server.new_session(123)
        with patch.object(server,'credentials',return_value=('token',{123})):
            self.assertEqual(server.session_user(token),123)
            with server.connect() as db:db.execute('UPDATE sessions SET expires=0')
            self.assertIsNone(server.session_user(token))

if __name__=='__main__':unittest.main()
