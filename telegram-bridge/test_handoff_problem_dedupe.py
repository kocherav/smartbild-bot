"""24.11: one rejected task file must be announced once, not again per branch after a merge."""
import unittest

import handoff_watcher as h


class ProblemsAnnouncedOnce(unittest.TestCase):
    def problem(self, ref):
        return {'ref': ref, 'path': 'handoff/inbox/TASK-20261123-05.md', 'error': 'summary', 'sha256': 'abc'}

    def test_same_file_on_main_after_merge_is_not_repeated(self):
        state = {'tasks': {}, 'problems': {}}
        self.assertEqual(1, len(h.plan([], [self.problem('origin/claude/x')], state)[2]))
        self.assertEqual([], h.plan([], [self.problem('origin/main'), self.problem('origin/claude/x')], state)[2])

    def test_legacy_ref_keyed_state_is_respected(self):
        state = {'tasks': {}, 'problems': {'origin/claude/x:handoff/inbox/TASK-20261123-05.md': 'abc'}}
        self.assertEqual([], h.plan([], [self.problem('origin/main')], state)[2])

    def test_changed_file_is_announced_again(self):
        state = {'tasks': {}, 'problems': {'handoff/inbox/TASK-20261123-05.md': 'old'}}
        self.assertEqual(1, len(h.plan([], [self.problem('origin/main')], state)[2]))


if __name__ == '__main__':
    unittest.main()
