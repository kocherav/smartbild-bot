import unittest
import generate_kp


class ManualLinesTest(unittest.TestCase):
    def test_manual_service_is_rendered_and_costed_without_discount(self):
        result = generate_kp.render_variant([{
            "source": "manual", "label": "Демонтаж блока", "unit": "шт.",
            "qty": 2, "unit_price": 8000, "cost_price": 5000,
        }], discount_pct=7, include_install=False)
        self.assertEqual(16000, result["total"])
        self.assertEqual(10000, result["economics"]["cost"])
        self.assertEqual("service", result["summary_items"][0]["type"])
        self.assertIn("Демонтаж блока", result["rows_html"][0])


if __name__ == "__main__": unittest.main()
