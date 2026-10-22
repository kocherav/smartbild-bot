import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import human_fixtures
from human_qa_harness import FakeMegaplan


DEAL = {'id': '887', 'name': 'Офис', 'description': 'Офис на Ленина', 'client': 'ООО «Бета»', 'address': 'Москва',
        'executors': ['Сергей'], 'status_id': '10', 'status': 'Новая', 'price': 120000.0, 'positions_count': 1,
        'transitions': [{'transition_id': 't', 'state_id': '11', 'name': 'Закупка', 'enabled': True}]}


def fake_crm(cmd, input=None, **_kwargs):
    script = Path(cmd[1]).name
    spec = json.loads(input)
    answers = {
        'deal_browser.py': {'ok': True, 'deal': DEAL},
        'payer_manager.py': {'ok': True, 'client_id': '42', 'client_name': 'ООО «Бета»', 'payers': [
            {'id': '1', 'name': 'ООО «Бета»', 'inn': '1', 'selected': True},
            {'id': '2', 'name': 'ООО «Бета Сервис»', 'inn': '2', 'selected': False}]},
        'contract_invoice.py': {'ok': True, 'invoices': [{'id': '55', 'number': '17', 'date': '01.10.2026',
                                                          'status': 'drawn', 'sum': 120000.0, 'rows_count': 1, 'line': None}]},
        'megaplan_api.py': {'ok': True, 'ledger': [{'name': 'Сплит', 'qty': 1, 'sell_price': 120000, 'cost_material': 80000}]},
    }
    assert spec.get('deal_id') == '887'
    return subprocess.CompletedProcess(cmd, 0, json.dumps(answers[script], ensure_ascii=False) + '\n', '')


class HumanFixtureTests(unittest.TestCase):
    def test_capture_is_read_only(self):
        with self.assertRaises(PermissionError):
            human_fixtures.crm_cli('payer_manager.py', {'deal_id': '1', 'payer_id': '2'}, runner=fake_crm)
        with self.assertRaises(PermissionError):
            human_fixtures.crm_cli('deal_browser.py', {'action': 'move_status', 'deal_id': '1'}, runner=fake_crm)

    def test_capture_register_verify_and_load(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            registry = root / 'HUMAN_JOURNEYS.json'
            registry.write_text(json.dumps({'journeys': [{'id': 'HUMAN-X', 'automated': True},
                                                         {'id': 'HUMAN-Y', 'automated': False}]}))
            snapshot, digest = human_fixtures.capture(['887'], root / 'fixtures' / 'crm.json', runner=fake_crm)
            human_fixtures.register(registry, root / 'fixtures' / 'crm.json', digest, snapshot['captured_at'])
            stored = json.loads(registry.read_text())
            self.assertEqual('crm-readonly', stored['journeys'][0]['fixture_provenance']['source'])
            self.assertNotIn('fixture_provenance', stored['journeys'][1])
            loaded, problem = human_fixtures.verified_snapshot(registry)
            self.assertIsNone(problem)
            crm = human_fixtures.load(FakeMegaplan(root), loaded)
            self.assertEqual('1', crm.deals['887']['payer_id'])
            self.assertEqual('ООО «Бета»', crm.summary(crm.deals['887'])['client'])
            self.assertEqual(120000.0, crm.price(crm.deals['887']))
            self.assertEqual(1, len(crm.invoices))
            (root / 'fixtures' / 'crm.json').write_text('{}')
            self.assertIsNone(human_fixtures.verified_snapshot(registry)[0])

    def test_live_journeys_run_on_a_captured_snapshot(self):
        import human_live_journeys
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            registry = root / 'HUMAN_JOURNEYS.json'
            registry.write_text(json.dumps({'journeys': [{'id': 'HUMAN-X', 'automated': True}]}))
            snapshot, digest = human_fixtures.capture(['887'], root / 'crm.json', runner=fake_crm)
            human_fixtures.register(registry, root / 'crm.json', digest, snapshot['captured_at'])
            with patch.object(human_live_journeys, 'REGISTRY', registry):
                suite = unittest.defaultTestLoader.loadTestsFromTestCase(human_live_journeys.LiveSnapshotJourneys)
                result = unittest.TestResult()
                suite.run(result)
            problems = [str(case) + '\n' + text[-1500:] for case, text in result.failures + result.errors]
            self.assertEqual([], problems)
            self.assertEqual(6, result.testsRun)


if __name__ == '__main__':
    unittest.main()
