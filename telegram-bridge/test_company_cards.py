import hashlib,json,tempfile,unittest
from pathlib import Path
from company_cards import handle_request

class CardsTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.file=self.root/'card.pdf';self.file.write_bytes(b'approved pdf')
        self.catalog=self.root/'own_companies.json'
        self.company={'name':'ИП Кочержинский А.В.','aliases':['ип кочержинский'],'requisites_card':{'path':'card.pdf','sha256':hashlib.sha256(self.file.read_bytes()).hexdigest()}}
        self.save([self.company]);self.sent=[];self.messages=[]
    def save(self,companies):self.catalog.write_text(json.dumps({'companies':companies}))
    def run_request(self,text='пришли мне карточку ИП Кочержинский',owner=True,transport=None):
        return handle_request(text,owner,transport or (lambda p,c:self.sent.append((p,c)) or True),self.messages.append,self.catalog)
    def test_phrases(self):
        for text in ['пришли мне карточку ИП Кочержинский','Отправь реквизиты ИП Кочержинский','Карточка ИП Кочержинский','Пришлите карточку ИП Кочержинский, пожалуйста']:
            self.assertTrue(self.run_request(text))
        self.assertEqual(len(self.sent),4)
    def test_other_role_and_payer(self):
        self.assertFalse(self.run_request(owner=False));self.assertFalse(self.run_request('Загрузить карточку плательщика'));self.assertFalse(self.run_request('создай сделку ИП Кочержинский'))
    def test_missing_and_changed(self):
        self.file.unlink();self.assertTrue(self.run_request());self.assertIn('недоступен',self.messages[-1]);self.assertFalse(self.sent)
        self.file.write_bytes(b'changed');self.run_request();self.assertIn('не совпадает',self.messages[-1]);self.assertFalse(self.sent)
    def test_delivery_retry(self):
        self.run_request(transport=lambda p,c:False);self.assertIn('Повторите',self.messages[-1]);self.run_request();self.assertEqual(len(self.sent),1)
    def test_ambiguity_and_no_card(self):
        self.save([self.company,{'name':'ООО Кливэл','aliases':['кливэл']}]);self.run_request('пришли нашу карточку');self.assertIn('Уточните',self.messages[-1]);self.run_request('пришли карточку Кливэл');self.assertIn('не сохранена',self.messages[-1])
    def test_bridge_entry(self):
        text=Path(__file__).with_name('bridge.py').read_text()
        segment=text.split('def process_business_message(',1)[1]
        self.assertLess(segment.index('handle_company_card_request('),segment.index('document_job = None'))
