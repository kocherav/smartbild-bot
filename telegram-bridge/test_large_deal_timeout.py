"""Owner 24.11: a 53-line spec was killed by the fixed 3-minute limit before the deal was written."""
import unittest
from unittest.mock import patch

import bridge


class LargeDealIsNotCutOff(unittest.TestCase):
    def test_limit_grows_with_the_spec(self):
        self.assertEqual(bridge.CREATE_MEGAPLAN_DEAL_TIMEOUT_SEC, bridge.create_deal_timeout([{}] * 2))
        self.assertGreaterEqual(bridge.create_deal_timeout([{}] * 53), 53 * 12 + 300)

    def test_subprocess_gets_the_scaled_limit(self):
        spec = {'client_name': 'Бюро', 'client_id': '1003030', 'client_kind': 'company', 'description': 'Проект',
                'tax_mode': 'none', 'items': [{'name': f'Позиция {i}', 'qty': 1, 'unit_price': 0} for i in range(53)]}
        seen = {}

        def fake_run(*args, **kwargs):
            seen['timeout'] = kwargs.get('timeout')
            raise bridge.subprocess.TimeoutExpired('x', kwargs.get('timeout'))
        with patch.object(bridge, 'RUNTIME_ACTIVE', False), \
             patch.object(bridge, 'price_install_addons', return_value=([], {}, [])), \
             patch.object(bridge.subprocess, 'run', side_effect=fake_run):
            bridge.run_create_megaplan_deal(spec)
        self.assertEqual(bridge.create_deal_timeout(spec['items']), seen['timeout'])


if __name__ == '__main__':
    unittest.main()
