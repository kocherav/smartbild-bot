"""Owner 24.11: supplier invoices give our cost, КП give the sale price and the cost by our discount."""
import unittest

import deal_price_sources as dps

LEDGER = [
    {'offer_row_id': '1', 'offer_id': '11', 'name': 'Диффузор щелевой Invisiline SMART-40-B-2000-2', 'sell_price': 0, 'cost_material': 0},
    {'offer_row_id': '2', 'offer_id': '12', 'name': 'Ниппель оцинкованный Ø125 мм, Галвент', 'sell_price': 0, 'cost_material': 0},
    {'offer_row_id': '3', 'offer_id': '13', 'name': 'Внутренний канальный блок mini-VRV Daikin FXSQ20A', 'sell_price': 0, 'cost_material': 0},
    {'offer_row_id': '4', 'offer_id': '14', 'name': 'Гидрозатвор канализационный HL 138', 'sell_price': 0, 'cost_material': 0},
    {'offer_row_id': '5', 'offer_id': '15', 'name': 'Клей K-Flex K414', 'sell_price': 900, 'cost_material': 600},
]
KP = {'kind': 'kp', 'discount': 15, 'supplier': 'Арктика', 'file': 'kp.pdf', 'rows': [
    {'name': 'Диффузор щелевой Invisiline SMART 40 B 2000 2', 'qty': 2, 'unit': 'шт', 'price': 40000}]}
INVOICE = {'kind': 'invoice', 'supplier': 'Вентрешения', 'file': 'inv.pdf', 'rows': [
    {'name': 'Ниппель(Кр) - 125', 'qty': 10, 'unit': 'шт', 'price': 150}]}


class Proposals(unittest.TestCase):
    def test_classify(self):
        self.assertEqual('invoice', dps.classify('Счет на оплату № 12 от 01.11.2026'))
        self.assertEqual('kp', dps.classify('Коммерческое предложение № 7'))
        self.assertIsNone(dps.classify('Спецификация'))

    def test_kp_discount_invoice_cost_catalog_and_untouched_priced_rows(self):
        daikin = lambda name: (250000, 180000, 'прайс Daichi, модель FXSQ20A') if 'FXSQ20A' in name else None
        result = dps.propose(LEDGER, [KP, INVOICE], history=[], ratios={}, catalog=daikin)
        by = {p['offer_row_id']: p for p in result['proposals']}
        self.assertEqual((40000, 34000.0), (by['1']['sell_price'], by['1']['cost_material']))
        self.assertIn('скидка 15%', by['1']['mark'])
        self.assertEqual((450.0, 150), (by['2']['sell_price'], by['2']['cost_material']))   # fitting +200 %
        self.assertEqual((250000, 180000), (by['3']['sell_price'], by['3']['cost_material']))
        self.assertNotIn('5', by)                                   # priced row with cost — not touched
        self.assertEqual(['Гидрозатвор канализационный HL 138'], [s['name'] for s in result['skipped']])


if __name__ == '__main__':
    unittest.main()
