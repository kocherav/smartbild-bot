"""Regression tests for the QA orchestrator -> browser runner boundary."""
import importlib.util
from pathlib import Path
import tempfile
import unittest


HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location('browser_runner', HERE / 'run_browser_checks.py')
RUNNER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUNNER)


class BrowserRunnerContractTest(unittest.TestCase):
    def test_qa_evidence_argument_and_allowed_ports_cover_all_browser_entries(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'browser-audit.json'
            self.assertEqual(RUNNER.arguments(['--evidence', str(target)]).evidence, target)
        self.assertTrue(all(48000 <= port <= 48999 for port in RUNNER.PORTS))
        sources = ''.join(path.read_text(encoding='utf-8') for path in HERE.glob('*.cjs'))
        self.assertNotIn('127.0.0.1:8097', sources)
        self.assertNotIn('127.0.0.1:8098', sources)
        for port in RUNNER.PORTS:
            self.assertIn(f'127.0.0.1:{port}', sources)


if __name__ == '__main__':
    unittest.main()
