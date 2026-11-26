"""26.11: a supplier invoice file ended in «техническая ошибка» — raw_user_text was set only for text."""
import ast
import os
import unittest

SOURCE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'bridge.py')


class RawUserTextIsAlwaysBound(unittest.TestCase):
    def test_assigned_before_any_branch_of_process_business_message(self):
        tree = ast.parse(open(SOURCE, encoding='utf-8').read())
        fn = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == 'process_business_message')
        first = [n for n in fn.body[:3] if isinstance(n, ast.Assign)]
        self.assertTrue(any(isinstance(t, ast.Name) and t.id == 'raw_user_text' for a in first for t in a.targets),
                        'raw_user_text must be bound at the top of process_business_message, not only in the text branch')


if __name__ == '__main__':
    unittest.main()
