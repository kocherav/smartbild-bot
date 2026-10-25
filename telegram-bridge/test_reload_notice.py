import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import bridge


CHANGELOG = """# Журнал

## 2026-10-25 — список сделок всегда с кнопками

текст

## 2026-10-25 — идеи тестировщика решаются кнопкой

## 2026-10-24 — старое
"""


class ReloadNoticeTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        folder = Path(self.temp.name)
        (folder / 'CHANGELOG.md').write_text(CHANGELOG, encoding='utf-8')
        self.code = folder / 'bridge.py'
        self.code.write_text('v1')
        for patcher in (patch.object(bridge, 'RELOAD_NOTICE_FILE', str(folder / 'reload_notice_state.json')),
                        patch.object(bridge, 'CHANGELOG_FILE', str(folder / 'CHANGELOG.md')),
                        patch.object(bridge, '__file__', str(self.code))):
            patcher.start()
            self.addCleanup(patcher.stop)

    def announce(self):
        with patch.object(bridge, 'send_message') as send:
            sent = bridge.announce_reload('t', 'owner')
        return sent, (send.call_args.args[2] if send.called else None)

    def test_new_version_is_announced_once_with_whats_new(self):
        sent, text = self.announce()
        self.assertTrue(sent)
        self.assertIn('🔄 Бот перезапущен на новой версии', text)
        self.assertIn('• список сделок всегда с кнопками', text)
        self.assertEqual((False, None), self.announce(), 'Перезапуск на той же версии — без сообщения')

    def test_next_version_lists_only_new_entries(self):
        self.announce()
        changelog = Path(bridge.CHANGELOG_FILE)
        changelog.write_text(CHANGELOG.replace('# Журнал\n', '# Журнал\n\n## 2026-10-26 — уведомление о перезапуске\n'),
                             encoding='utf-8')
        self.code.write_text('v2')
        sent, text = self.announce()
        self.assertTrue(sent)
        self.assertIn('• уведомление о перезапуске', text)
        self.assertNotIn('список сделок', text)


if __name__ == '__main__':
    unittest.main()
