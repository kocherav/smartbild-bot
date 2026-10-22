import unittest

from generate_contract import classify_position, contract_data


def position(identifier, name, total, purchase=0, labour=0):
    return {
        "id": str(identifier), "name": name, "quantity": 1,
        "price": {"value": total}, "sum": {"value": total},
        "offer": {
            "Category1000045CustomFieldTsenaZakupki": {"value": purchase},
            "Category1000045CustomFieldSebesRabot": {"value": labour},
        },
    }


class ContractPositionTypesTests(unittest.TestCase):
    def test_electrical_labour_is_not_goods(self):
        rows = [
            ("Монтаж кабельного лотка", 45600),
            ("Прокладка кабеля по лотку", 38000),
            ("Алмазное бурение отверстия", 42500),
            ("Монтаж накладного щита", 10000),
            ("Сборка и внутренняя коммутация щита", 22000),
            ("Оконцевание, опрессовка и подключение кабеля", 8000),
            ("Устройство перемычек уравнивания потенциалов", 6000),
            ("Огнезаделка кабельных проходок", 12500),
            ("Электроизмерения", 8000),
        ]
        positions = [position(i, name, amount, labour=100) for i, (name, amount) in enumerate(rows)]
        positions += [
            position(20, "Доставка оборудования и материалов", 15000, purchase=9000),
            position(21, "Монтажные расходные материалы", 4500, purchase=3000),
        ]
        data = contract_data({"positions": positions, "price": {"value": 212100}}, {})
        self.assertEqual(data["works"], 207600)
        self.assertEqual(data["materials"], 4500)
        self.assertEqual(data["advance"] + data["works"], data["total"])

    def test_goods_with_installation_in_name_are_not_labour(self):
        self.assertEqual(classify_position(position(1, "Монтажная коробка", 500, purchase=200)), "material")

    def test_unknown_labour_name_uses_structured_cost(self):
        self.assertEqual(classify_position(position(1, "Испытания системы", 500, labour=200)), "work")

    def test_explicit_override_remains_authoritative(self):
        row = position(1, "Доставка", 500, purchase=200)
        data = contract_data({"positions": [row], "price": {"value": 500}}, {"position_types": {"1": "material"}})
        self.assertEqual(data["materials"], 500)

    def test_no_cost_fields_uses_service_name(self):
        self.assertEqual(classify_position({"name": "Прокладка кабеля"}), "work")
        self.assertEqual(classify_position({"name": "Автомат ABB"}), "equipment")


if __name__ == "__main__":
    unittest.main()
