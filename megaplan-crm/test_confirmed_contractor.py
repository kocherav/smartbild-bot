import unittest
from unittest.mock import Mock
from megaplan_api import MegaplanAPI


class ConfirmedContractorTest(unittest.TestCase):
    def setUp(self):
        self.api = object.__new__(MegaplanAPI)
        self.api.search_contractors = Mock(return_value=[{'id': '42', '_contractor_kind': 'company'}])
        self.api.find_or_create_contractor = Mock(return_value=('new', 'human'))

    def test_id_not_name_controls_selection(self):
        self.assertEqual(('42', 'company'), self.api.resolve_confirmed_contractor({'client_name': 'Example', 'client_id': '42'}))
        self.api.find_or_create_contractor.assert_not_called()

    def test_missing_and_stale_identity_do_not_create(self):
        for extra in ({}, {'client_id': '99'}, {'allow_new_client': True}):
            with self.assertRaises(ValueError): self.api.resolve_confirmed_contractor({'client_name': 'Example', **extra})
        self.api.find_or_create_contractor.assert_not_called()

    def test_empty_search_requires_explicit_new_permission(self):
        self.api.search_contractors.return_value = []
        with self.assertRaises(ValueError): self.api.resolve_confirmed_contractor({'client_name': 'Example'})
        self.assertEqual(('new', 'human'), self.api.resolve_confirmed_contractor({'client_name': 'Example', 'allow_new_client': True, 'client_kind': 'human'}))

    def test_failed_search_never_creates(self):
        self.api.search_contractors.side_effect = TimeoutError
        with self.assertRaises(TimeoutError): self.api.resolve_confirmed_contractor({'client_name': 'Example', 'allow_new_client': True})
        self.api.find_or_create_contractor.assert_not_called()


if __name__ == '__main__': unittest.main()
