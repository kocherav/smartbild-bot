import unittest
from unittest.mock import Mock
import daichi_catalog_cache as cache


class RefreshTests(unittest.TestCase):
    def test_all_pages_including_last_partial_page(self):
        api = Mock()
        def page(*, page, page_size):
            self.assertEqual(page_size, 100)
            return {'total_count': 253, 'data': {str(i): {'id': i} for i in range((page-1)*100, min(page*100, 253))}}
        api.get_productparams.side_effect = page
        self.assertEqual(len(cache._refresh_productparams(api)), 253)
        self.assertEqual(api.get_productparams.call_count, 3)

    def test_failed_page_is_not_treated_as_complete_catalog(self):
        api = Mock()
        api.get_productparams.side_effect = [{'total_count': 101, 'data': {str(i): {} for i in range(100)}}, TimeoutError()]
        with self.assertRaises(TimeoutError):
            cache._refresh_productparams(api)

    def test_missing_page_is_not_treated_as_complete_catalog(self):
        api = Mock()
        api.get_productparams.side_effect = [{'total_count': 101, 'data': {str(i): {} for i in range(100)}}, {'data': {}}]
        with self.assertRaises(ValueError):
            cache._refresh_productparams(api)
