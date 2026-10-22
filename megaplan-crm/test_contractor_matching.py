import unittest
from unittest import mock

from megaplan_api import MegaplanAPI, comparable_contractor_name


class ContractorMatchingTest(unittest.TestCase):
    def api(self, responses):
        api = object.__new__(MegaplanAPI)
        def reply(method, path, params=None, **kwargs):
            self.assertEqual('GET', method, 'Lookup test must never create a client')
            self.assertTrue(path.endswith('/search'))
            return responses[1] if params.get('q') == 'jetcar' and path.startswith('/contractorCompany/') else responses[0]
        api._call = mock.Mock(side_effect=reply)
        return api

    def test_cyrillic_jetcar_reuses_existing_latin_client(self):
        api = self.api([
            {"data": []},
            {"data": [{"id": "1002845", "name": "Автосалон JetCar"}]},
        ])
        result = api.find_or_create_contractor("Джеткар", "company")
        self.assertEqual(result, ("1002845", "company"))
        self.assertGreaterEqual(api._call.call_count, 4)
        api._call.assert_any_call("GET", "/contractorCompany/search", params={"q": "jetcar"})

    def test_ambiguous_phonetic_matches_do_not_create_client(self):
        candidates = [
            {"id": "1", "name": "JetCar Москва"},
            {"id": "2", "name": "JetCar Сервис"},
        ]
        api = self.api([{"data": []}, {"data": candidates}])
        with self.assertRaisesRegex(ValueError, "несколько похожих клиентов"):
            api.find_or_create_contractor("Джеткар", "company")
        self.assertGreaterEqual(api._call.call_count, 4)

    def test_comparable_names_cover_cyrillic_and_latin(self):
        self.assertIn(comparable_contractor_name("Джеткар"), comparable_contractor_name("Автосалон JetCar"))


if __name__ == "__main__":
    unittest.main()
