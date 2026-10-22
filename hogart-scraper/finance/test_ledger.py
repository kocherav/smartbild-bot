import copy, importlib.util, json, tempfile, unittest, zipfile
from pathlib import Path
import ledger

class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.db=ledger.connect(self.root/'db')
    def tearDown(self):self.db.close();self.temp.cleanup()
    def statement(self,amount='100.00',purpose='Оплата',number='1',end='02.10.2026',movement='01.10.2026'):
        return ('1CClientBankExchange\nВерсияФормата=1.03\nКодировка=Windows\nДатаНачала=01.10.2026\nДатаКонца='+end+'\nРасчСчет=111\nСекцияРасчСчет\nРасчСчет=111\nДатаНачала=01.10.2026\nДатаКонца='+end+'\nНачальныйОстаток=1000.00\nВсегоПоступило=0.00\nВсегоСписано='+amount+'\nКонечныйОстаток='+str((100000-ledger.cents(amount))/100)+'\nКонецРасчСчет\nСекцияДокумент=Платежное поручение\nНомер='+number+'\nДата=01.10.2026\nСумма='+amount+'\nПлательщикСчет=111\nПолучательСчет=222\nПлательщикИНН=123\nПолучательИНН=456\nДатаСписано='+movement+'\nДатаПоступило=\nНазначениеПлатежа='+purpose+'\nКонецДокумента\nКонецФайла\n').encode('cp1251')
    def archive(self,raw,name='test.zip'):
        p=self.root/name
        with zipfile.ZipFile(p,'w') as z:z.writestr('statement.txt',raw)
        return p
    def test_repeat(self):
        p=self.archive(self.statement());first=ledger.import_zip(self.db,p)
        self.assertEqual(first['new'],1);self.assertEqual(len(first['new_ids']),1)
        repeated=ledger.import_zip(self.db,p)
        self.assertEqual({k:repeated[k] for k in ('new','repeated','statements')},{'new':0,'repeated':1,'statements':1})
        self.assertEqual(repeated['new_ids'],[])
        self.assertEqual(first['statement_details'],[{'account':'111','start':'2026-10-01','end':'2026-10-02'}])
    def test_changed_purpose_quarantined(self):
        ledger.import_zip(self.db,self.archive(self.statement()))
        with self.assertRaises(ValueError):ledger.import_zip(self.db,self.archive(self.statement(purpose='Исправлено')))
        self.assertEqual(self.db.execute('SELECT count(*) FROM statements').fetchone()[0],1)
    def test_changed_amount_quarantined(self):
        ledger.import_zip(self.db,self.archive(self.statement()))
        with self.assertRaises(ValueError):ledger.import_zip(self.db,self.archive(self.statement(amount='101.00')))
        self.assertEqual(self.db.execute('SELECT count(*) FROM operations').fetchone()[0],1)
    def test_balances(self):
        with self.assertRaises(ValueError):ledger.parse(self.statement().replace(b'900.0',b'899.0'))
    def test_incomplete(self):
        with self.assertRaises(ValueError):ledger.parse(self.statement().replace('КонецФайла'.encode('cp1251'),b''))
    def test_date_outside(self):
        with self.assertRaises(ValueError):ledger.parse(self.statement(movement='03.10.2026'))
    def test_atomic_archive(self):
        p=self.root/'bad.zip'
        with zipfile.ZipFile(p,'w') as z:
            z.writestr('valid.txt',self.statement());z.writestr('bad.txt',b'bad')
        with self.assertRaises(ValueError):ledger.import_zip(self.db,p)
        self.assertEqual(self.db.execute('SELECT count(*) FROM operations').fetchone()[0],0)
    def test_mirrored_accounts_kept(self):
        a=self.statement();b=a.decode('cp1251').replace('РасчСчет=111','РасчСчет=222').replace('ВсегоПоступило=0.00','ВсегоПоступило=100.00').replace('ВсегоСписано=100.00','ВсегоСписано=0.00').replace('КонечныйОстаток=900.0','КонечныйОстаток=1100.00').replace('ДатаСписано=01.10.2026','ДатаСписано=').replace('ДатаПоступило=','ДатаПоступило=01.10.2026')
        p=self.root/'pair.zip'
        with zipfile.ZipFile(p,'w') as z:z.writestr('a.txt',a);z.writestr('b.txt',b.encode('cp1251'))
        self.assertEqual(ledger.import_zip(self.db,p)['new'],2)
    def test_invoice_refs(self):
        self.assertEqual(ledger.invoice_refs('Оплата по счёту №79566, 79567 от 22 сентября 2026. В том числе НДС 22%, 45387.15 руб.'), ['79566','79567'])
        self.assertEqual(ledger.invoice_refs('Оплата по счёту №42965 от 08 мая 2026 к договору №1939. В том числе НДС 22%, 9454.79 руб.'), ['42965'])
        self.assertEqual(ledger.invoice_refs('Оплата по счёту № В том числе НДС 22%, 10887.25 руб.'), [])
        self.assertEqual(ledger.invoice_refs('Оплата по счету ПКБ-1843 от 06.05.2026, ПКБ-5319 от 16.12.2025г, В том числе НДС 22%, 1782.17 руб.'), ['ПКБ-1843','ПКБ-5319'])
    def test_decimal(self):
        self.assertEqual(ledger.cents('0.29'),29)
        with self.assertRaises(ValueError):ledger.cents('1.001')

if __name__=='__main__':unittest.main()
