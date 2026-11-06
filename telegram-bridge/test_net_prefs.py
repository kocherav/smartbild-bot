import socket
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import net_prefs

V6 = (socket.AF_INET6, socket.SOCK_STREAM, 6, '', ('2001:67c:4e8:f004::9', 443, 0, 0))
V4 = (socket.AF_INET, socket.SOCK_STREAM, 6, '', ('149.154.167.220', 443))


class PreferIpv4Test(unittest.TestCase):
    """06.11: an unreachable IPv6 route cost 5 s per message (40 s per long call)."""

    def setUp(self):
        net_prefs._cache.clear()
        self.addCleanup(net_prefs._cache.clear)

    def test_ipv4_comes_first_and_ipv6_stays_as_fallback(self):
        with patch.object(net_prefs, '_original', return_value=[V6, V4]):
            self.assertEqual([V4, V6], net_prefs.getaddrinfo('api.telegram.org', 443))

    def test_repeated_lookup_is_served_from_memory(self):
        with patch.object(net_prefs, '_original', return_value=[V4]) as lookup:
            net_prefs.getaddrinfo('api.telegram.org', 443)
            net_prefs.getaddrinfo('api.telegram.org', 443)
        self.assertEqual(1, lookup.call_count)

    def test_can_be_switched_off(self):
        with patch.dict('os.environ', {'BRIDGE_PREFER_IPV4': '0'}), patch.object(socket, 'getaddrinfo', net_prefs._original):
            self.assertFalse(net_prefs.install())


class TelegramHealthTest(unittest.TestCase):
    def test_slow_and_failed_calls_reach_the_digest_line(self):
        import bridge
        with tempfile.TemporaryDirectory() as folder, \
             patch.object(bridge, 'TELEGRAM_HEALTH_FILE', str(Path(folder) / 'telegram_health_state.json')):
            self.assertEqual('', bridge.telegram_health_line())
            bridge.record_telegram_health('sendMessage', 5.13, False)
            bridge.record_telegram_health('sendMessage', 0.1, False)
            bridge.record_telegram_health('getUpdates', 40, True)
            bridge.record_telegram_health('sendMessage', 40.3, True)
            line = bridge.telegram_health_line()
        self.assertIn('медленных ответов (> 2 с) — 1', line)
        self.assertIn('сбоев — 1', line)
        self.assertIn('40.3', line)


if __name__ == '__main__':
    unittest.main()
