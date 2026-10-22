import json
import os
import tempfile
import unittest

from sync_deal_to_contract import load_snapshot, match_rows


class SignedContractSyncTests(unittest.TestCase):
    def test_snapshot_total_is_a_strict_control(self):
        fd, path = tempfile.mkstemp(suffix='.json')
        os.close(fd)
        try:
            with open(path, 'w', encoding='utf-8') as out:
                json.dump({'total': 101, 'rows': [{'name': 'Кабель', 'qty': 2, 'unit_price': 50}]}, out)
            with self.assertRaisesRegex(ValueError, 'не равна'):
                load_snapshot(path)
        finally:
            os.unlink(path)

    def test_rows_are_matched_by_normalized_name_without_partial_matches(self):
        deal_rows = [
            {'id': '1', 'offer': {'name': 'Наружный\u00a0блок Daikin'}},
            {'id': '2', 'offer': {'name': 'Кабель МКЭШ 3х0,75'}},
        ]
        contract_rows = [
            {'name': 'Наружный блок Daikin', 'qty': 1, 'unit_price': 1},
            {'name': 'Кабель МКЭШ 3х0,75', 'qty': 1, 'unit_price': 1},
        ]
        pairs = match_rows(deal_rows, contract_rows)
        self.assertEqual(['1', '2'], [actual['id'] for actual, _ in pairs])

    def test_extra_live_row_blocks_unsafe_replacement(self):
        with self.assertRaisesRegex(ValueError, 'лишние'):
            match_rows(
                [{'id': '1', 'offer': {'name': 'Кабель'}}, {'id': '2', 'offer': {'name': 'Лишняя'}}],
                [{'name': 'Кабель', 'qty': 1, 'unit_price': 1}],
            )


if __name__ == '__main__':
    unittest.main()
