import unittest
from unittest.mock import patch

import payer_manager


CARD = {
    "name": 'ООО "МК"', "inn": "7733356410", "kpp": "772101001",
    "ogrn": "1207700225435", "legalAddress": "Москва",
    "currentAccount": "40702810838000164830", "bank": "ПАО Сбербанк",
    "bik": "044525225", "correspondentAccount": "30101810400000000225",
}


class FakeAPI:
    def __init__(self, payers=None):
        self.payers = payers or []
        self.calls = []

    def _call(self, method, path, params=None, json_body=None):
        self.calls.append((method, path, json_body))
        if path in ("/contractorCompany/search", "/contractorHuman/search"):
            return {"data": ([{"contentType": "ContractorCompany", "id": "1002845", "name": "Светлана Дикушина"}]
                             if path == "/contractorCompany/search" else [])}
        if path == "/deal/887" and method == "GET":
            return {"data": {"id": "887", "payer": {"id": "1003023", "name": CARD["name"]}, "contractor": {
                "contentType": "ContractorCompany", "id": "1002845", "name": "Клиент",
            }}}
        if path == "/contractorCompany/1002845":
            return {"data": {"payers": self.payers}}
        if path == "/contractorCompany/1002845/payers":
            return {"data": {"id": "1004000", **json_body}}
        if path == "/deal/887" and method == "POST":
            return {"data": {"id": "887"}}
        if path.startswith("/payer/") and method == "POST":
            return {"data": {"id": path.rsplit('/', 1)[-1], **json_body}}
        raise AssertionError((method, path))

    def deal_url(self, deal_id):
        return f"https://example.test/deals/{deal_id}/card/"


class PayerManagerTests(unittest.TestCase):
    def test_lists_only_payers_of_deal_client_and_marks_current(self):
        api = FakeAPI([
            {"id": "1003023", "name": 'ООО "МК"', "inn": "7733356410"},
            {"id": "1003408", "name": 'ООО "БАРИОН"', "inn": "7727727824"},
        ])
        result = payer_manager.apply({"action": "list_deal_payers", "deal_id": "887"}, api)
        self.assertEqual(result["client_name"], "Клиент")
        self.assertEqual([item["id"] for item in result["payers"]], ["1003023", "1003408"])
        self.assertEqual([item["selected"] for item in result["payers"]], [True, False])

    def test_creates_and_links_payer(self):
        api = FakeAPI()
        result = payer_manager.apply({"deal_id": "887", "payer": CARD}, api)
        self.assertTrue(result["created"])
        self.assertEqual(api.calls[-1][2]["payer"]["id"], "1004000")
        create_payload = next(body for method, path, body in api.calls if path.endswith("/payers"))
        self.assertEqual(create_payload["inn"], "7733356410")
        self.assertEqual(create_payload["contractor"]["id"], "1002845")

    def test_reuses_exact_taxpayer_and_account(self):
        api = FakeAPI([{"id": "1003023", **CARD}])
        result = payer_manager.apply({"deal_id": 887, "payer": CARD}, api)
        self.assertFalse(result["created"])
        self.assertFalse(any(path.endswith("/payers") for _, path, _ in api.calls))
        self.assertEqual(api.calls[-1][2]["payer"]["id"], "1003023")

    def test_rejects_bad_inn_before_writes(self):
        api = FakeAPI()
        with self.assertRaisesRegex(ValueError, "контрольных цифр"):
            payer_manager.apply({"deal_id": "887", "payer": {**CARD, "inn": "7701234567"}}, api)
        self.assertEqual(api.calls, [])

    def test_creates_in_named_client_without_deal(self):
        api = FakeAPI()
        result = payer_manager.apply({"client_name": "Светлана Дикушина", "payer": CARD}, api)
        self.assertTrue(result["created"])
        self.assertFalse(result["attached"])
        self.assertIsNone(result["deal_id"])
        self.assertFalse(any(path.startswith("/deal/") for _, path, _ in api.calls))

    def test_links_existing_payer_by_name(self):
        api = FakeAPI([{**CARD, "id": "1003408", "name": 'ООО "БАРИОН"'}])
        result = payer_manager.apply({"deal_id": "887", "payer_name": 'ООО "БАРИОН"'}, api)
        self.assertTrue(result["attached"])
        self.assertFalse(result["created"])
        self.assertEqual(api.calls[-1][2]["payer"]["id"], "1003408")

    def test_existing_payer_gets_director_from_new_card(self):
        existing = {"id": "1003023", **CARD}
        api = FakeAPI([existing])
        result = payer_manager.apply({"deal_id": "887", "payer": {**CARD, "director": "Иванова Мария Петровна"}}, api)
        self.assertFalse(result["created"])
        update = next(body for method, path, body in api.calls if path == "/payer/1003023")
        self.assertEqual(update[payer_manager.DIRECTOR_FIELD], "Иванова Мария Петровна")
        self.assertEqual(result["director"], "Иванова Мария Петровна")

    def test_new_payer_returns_saved_director_for_user_confirmation(self):
        api = FakeAPI()
        result = payer_manager.apply({
            "deal_id": "887", "payer": {**CARD, "director": "Иванова Мария Петровна"},
        }, api)
        self.assertEqual(result["director"], "Иванова Мария Петровна")

    def test_saves_deal_signatory_to_selected_payer(self):
        api = FakeAPI()
        result = payer_manager.apply({"action": "save_director", "deal_id": "887", "director": "Иванова Мария Петровна"}, api)
        self.assertTrue(result["saved"])
        self.assertEqual(api.calls[-1][1], "/payer/1003023")

    def test_saves_complete_signatory_profile_for_reuse(self):
        api = FakeAPI()
        with patch("payer_manager.save_signatory_profile") as save_profile:
            result = payer_manager.apply({
                "action": "save_signatory", "deal_id": "887",
                "director": "Иванова Мария Петровна",
                "position": "Генеральный директор", "authority": "Устав",
            }, api)
        self.assertTrue(result["saved"])
        save_profile.assert_called_once_with(
            "1003023", "Иванова Мария Петровна", "Генеральный директор", "Устав",
        )


if __name__ == "__main__":
    unittest.main()
