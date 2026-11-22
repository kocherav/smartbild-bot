"""22.11: a timed-out developer call must not wait for grandchildren holding its pipes."""
import subprocess
import sys
import time
import unittest
from unittest.mock import patch

import process_tree


class ProcessTreeTests(unittest.TestCase):
    def test_normal_run_returns_output(self):
        fake = type('P', (), {'pid': 1, 'returncode': 0, 'communicate': lambda self, input=None, timeout=None: ('ок', '')})()
        with patch.object(process_tree.subprocess, 'Popen', return_value=fake) as popen:
            result = process_tree.run(['x'], timeout=5, input='q')
        self.assertEqual(('ок', 0), (result.stdout, result.returncode))
        self.assertTrue(popen.call_args.kwargs['start_new_session'], 'своя группа процессов')

    def test_timeout_kills_the_whole_group_and_does_not_hang(self):
        calls = []

        class Stuck:
            pid = 4242
            returncode = None

            def communicate(self, input=None, timeout=None):
                calls.append(timeout)
                raise subprocess.TimeoutExpired('x', timeout)

        with patch.object(process_tree.subprocess, 'Popen', return_value=Stuck()), \
             patch.object(process_tree.os, 'killpg') as killpg:
            with self.assertRaises(subprocess.TimeoutExpired):
                process_tree.run(['x'], timeout=1, grace=0)
        self.assertEqual([process_tree.signal.SIGTERM, process_tree.signal.SIGKILL],
                         [c.args[1] for c in killpg.call_args_list])
        self.assertTrue(all(c.args[0] == 4242 for c in killpg.call_args_list))
        self.assertEqual(3, len(calls), 'ожидание ограничено, не бесконечно')


if __name__ == '__main__':
    unittest.main()
