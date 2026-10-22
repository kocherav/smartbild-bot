import tempfile
import unittest
from pathlib import Path

from payer_signatory_store import get_signatory, save_signatory


class PayerSignatoryStoreTests(unittest.TestCase):
    def test_profile_is_reused_only_by_exact_payer_id(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "profiles.json"
            lock = Path(directory) / "profiles.lock"
            save_signatory("1003023", "Ильинов Сергей Александрович",
                           "Генеральный директор", "Устав", path, lock)
            self.assertEqual(get_signatory("1003023", path), {
                "name": "Ильинов Сергей Александрович",
                "position": "Генеральный директор",
                "authority": "Устав",
            })
            self.assertEqual(get_signatory("another", path), {
                "name": "", "position": "", "authority": "",
            })

    def test_incomplete_profile_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "ФИО, должность"):
                save_signatory("1003023", "Ильинов Сергей Александрович", "", "Устав",
                               Path(directory) / "profiles.json", Path(directory) / "lock")


if __name__ == "__main__":
    unittest.main()
