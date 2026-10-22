"""The QA stand must never read or write production business stores."""
import unittest

import human_qa_harness
from human_qa_harness import Stand, say
from test_human_journeys import office


class StandIsolationTests(unittest.TestCase):
    def test_production_store_patterns(self):
        for path in ('/home/kocher.av/hogart-scraper/finance/review_registry.json',
                     '/home/kocher.av/telegram-bridge/workflow_runtime.sqlite3',
                     '/home/kocher.av/telegram-bridge/invoice_tasks.json',
                     '/home/kocher.av/telegram-bridge/.env',
                     '/home/kocher.av/hogart-scraper/incoming/card.pdf',
                     '/home/kocher.av/telegram-bridge/docs/architecture/human-fixtures/crm.json'):
            with self.subTest(path=path):
                self.assertTrue(human_qa_harness.production_store(path))
        for path in ('/home/kocher.av/megaplan-crm/tax_policies.json',
                     '/home/kocher.av/megaplan-crm/own_companies.json',
                     '/home/kocher.av/telegram-bridge/bridge.py',
                     '/home/kocher.av/telegram-bridge/docs/architecture/HUMAN_JOURNEYS.json'):
            with self.subTest(path=path):
                self.assertFalse(human_qa_harness.production_store(path))

    def test_reading_a_production_store_during_a_journey_is_blocked_and_recorded(self):
        outcome = {}

        def journey(person):
            try:
                open('/home/kocher.av/hogart-scraper/finance/review_registry.json').close()
            except PermissionError as exc:
                outcome['blocked'] = str(exc)
            except OSError as exc:
                outcome['unguarded'] = str(exc)
            yield say('/status')

        stand = Stand()
        self.addCleanup(stand.close)
        office(stand.crm)
        stand.run(journey)
        self.assertIn('рабочего хранилища', outcome.get('blocked', ''))
        self.assertEqual(['read:/home/kocher.av/hogart-scraper/finance/review_registry.json'], stand.blocked_writes)


if __name__ == '__main__':
    unittest.main()
