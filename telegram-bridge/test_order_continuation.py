import unittest
from order_continuation import requested,parse,question
class OrderContinuationTests(unittest.TestCase):
 def test_explicit_order(self):
  self.assertTrue(requested({'user_request':'Создай сделку, договор и счёт на 100 процентную оплату'}))
  self.assertFalse(requested({'user_request':'Создай сделку'}))
 def test_batched_answer(self):
  self.assertEqual(parse('Дата: 20.10.2026\nАдрес: Москва\nПлательщик: ООО Клиент'),{'date':'20.10.2026','address':'Москва','payer':'ООО Клиент'})
 def test_question_contains_only_missing(self):
  q=question({'deal_id':'1','missing':['Адрес'],'payers':[]})
  self.assertIn('Адрес:',q);self.assertNotIn('Дата:',q)

class RecoveryHintTests(__import__('unittest').TestCase):
 def test_uncertain_does_not_offer_blind_retry(self):
  import order_continuation
  text=order_continuation.recovery_hint({'requires_reconciliation':True})
  self.assertIn('до сверки',text);self.assertNotIn('Напишите',text)
 def test_retryable_suggests_resume(self):
  import order_continuation
  self.assertIn('Напишите',order_continuation.recovery_hint({'no_effect':True}))
