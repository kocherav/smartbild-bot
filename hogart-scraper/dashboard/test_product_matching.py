import unittest
from product_matching import compare
class ProductMatchingTests(unittest.TestCase):
 def test_format(self):
  for a,b in [('DKC Держатель д.50мм','DKC Держатель д.50 мм'),('Труба. д.20мм,100м','Труба, д.20 мм, 100 м')]:self.assertTrue(compare(a,b)['same'])
 def test_breakers(self):
  self.assertTrue(compare('Автоматический выключатель ABB 1-полюсный S201 C10','АВВ S201 С10 А')['same'])
  self.assertTrue(compare('Дифавтомат ABB DS201 C16 AC30 2-полюсный характеристика C 16A 30mA тип АС (2CSR255040R1164)','АВВ диф.автом. DS201 C16 AC30 выключатель')['same'])
 def test_conflicts(self):
  for a,b in [('ABB S201 C10','ABB S201 C16'),('ABB S803P C125','ABB S803 C125'),('DKC д.20мм','DKC д.50 мм'),('Кабель F/UTP 0,52','Кабель U/UTP 0,5'),('ABB DS201 C16 AC30','ABB DS201 C16 A30'),('ABB S201 C10 1-полюсный','ABB S201 C10 2-полюсный')]:
   self.assertFalse(compare(a,b)['same']);self.assertTrue(compare(a,b)['conflicts'],(a,b))
 def test_unknown(self):self.assertFalse(compare('Неизвестное изделие','Другое название')['same'])
 def test_pdf_wrap_inside_model_is_not_a_different_sku(self):
  result=compare('ARPV-LG24240-LINEAR-PFC-DA LI2-PD (24V, 10A, 240W)','ARPV-LG24240-LINEAR-PFC-DALI2-PD (24V, 10A, 240W)')
  self.assertTrue(result['same']);self.assertEqual(result['conflicts'],[])
 def test_decimal_dimension_followed_by_letters_is_not_truncated(self):
  from product_matching import attributes
  self.assertEqual(attributes('ВВГ-Пнг(А)-LS 2Х1.5ок(N)-0.660')['размеры'],{'2x1.5'})
  self.assertTrue(compare('Кабель 2х1,5','Кабель 2х1ок')['conflicts'])
