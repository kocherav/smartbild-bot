import unittest
from inventory import scan, render

class InventoryTest(unittest.TestCase):
    def test_extracts_keyboard_and_state_without_execution(self):
        source = '''
raise RuntimeError("must not execute")
MAIN_KEYBOARD = {"keyboard": [[{"text": "Menu"}]]}
def route(value):
    if value == "Menu":
        update_deal_ui_state("chat", pending="choose", deal_id=None)
'''
        data = scan(source)
        self.assertEqual(data['menus'][0]['buttons'], ['Menu'])
        self.assertEqual(data['state_writes'][0]['fields']['pending'], "'choose'")
        self.assertEqual(len(data['branches']), 1)
        self.assertIn('Menu', render(data))

    def test_internal_calls_and_hash_deterministic(self):
        source = 'def first():\n    second()\ndef second():\n    pass\n'
        data = scan(source)
        self.assertEqual(data['calls'][0]['to'], 'second')
        self.assertEqual(data, scan(source))
        self.assertNotEqual(data['sha256'], scan(source + '\n')['sha256'])

    def test_current_dialog_states_have_explicit_scenarios(self):
        import scenario_contracts as s
        result=s.inventory(s.BRIDGE.read_text(encoding='utf-8'))
        self.assertGreater(len(result['states']),50)
        self.assertEqual('KP-DEAL',result['states']['deal_sync_confirm']['scenario'])

    def test_external_ui_constants_are_classified(self):
        import scenario_contracts as s
        result=s.inventory(s.BRIDGE.with_name('legacy_report_ui.py').read_text())
        self.assertEqual('MNT-LEGACY',result['states']['installer_report_bundle_confirm']['scenario'])
        self.assertIn('installer_report_bundle_map',result['states'])

if __name__ == '__main__':
    unittest.main()
