import json, tempfile, unittest
from pathlib import Path
from daily_notice import import_notice


class NoticeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);(self.root/'reports').mkdir()
        row={'id':'new','company':'КЛИВЭЛ','date':'2026-10-09','number':'42','direction':'out','amount_cents':12345,
             'counterparty':'Поставщик','category':'Материалы','status':'Требует уточнения','flags':['Указать объект']}
        (self.root/'reports/ledger.json').write_text(json.dumps([row]))
        self.status={'imports':[{'new':1,'repeated':2,'new_ids':['new']}],
                     'report':{'owner_questions':['Для какого объекта платёж №42?'],'assistant_queue':[]}}

    def test_concrete_operation_and_owner_question(self):
        text=import_notice(self.status,self.root)
        for expected in ['№42','Поставщик','123,45 ₽','Указать объект','Для какого объекта','Разнесение_выписок.xlsx','лист «Вам»','2 повторов']:
            self.assertIn(expected,text)
        self.assertNotIn('Неоднозначные позиции оставлены',text)

    def test_no_questions_is_not_an_invented_review_request(self):
        self.status['report']['owner_questions']=[]
        self.status['report']['assistant_queue']=[{'group':'Q001','company':'КЛИВЭЛ','counterparty':'Банк','count':2,'amount':100,'reason':'Нужна встречная выписка'}]
        text=import_notice(self.status,self.root)
        self.assertIn('От вас сейчас действий не требуется',text)
        self.assertIn('Нужна встречная выписка',text)
        self.assertIn('по всему реестру',text)

    def test_report_failure_does_not_claim_updated_report_or_no_questions(self):
        self.status['report']=None
        text=import_notice(self.status,self.root)
        self.assertIn('Обновление Excel-отчёта не подтверждено',text)
        self.assertNotIn('Открытых вопросов к вам нет',text)
        self.assertNotIn('он приложен',text)
