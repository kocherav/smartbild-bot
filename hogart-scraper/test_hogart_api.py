import json
import os
import tempfile
import time
import unittest
from unittest import mock

import hogart_api


class HogartTokenTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.env_path = os.path.join(self.directory.name, ".env")
        self.token_path = os.path.join(self.directory.name, "token.json")
        with open(self.env_path, "w", encoding="utf-8") as target:
            target.write("HOGART_PHONE=test\nHOGART_PASSWORD=test\n")
        self.patches = [
            mock.patch.object(hogart_api, "ENV_FILE", self.env_path),
            mock.patch.object(hogart_api, "TOKEN_FILE", self.token_path),
        ]
        for patch in self.patches:
            patch.start()

    def tearDown(self):
        for patch in reversed(self.patches):
            patch.stop()
        self.directory.cleanup()

    def write_token(self, age_seconds):
        with open(self.token_path, "w", encoding="utf-8") as target:
            json.dump({"token": "cached"}, target)
        timestamp = time.time() - age_seconds
        os.utime(self.token_path, (timestamp, timestamp))

    def test_recent_cached_token_is_loaded(self):
        self.write_token(60)
        api = hogart_api.HogartAPI()
        self.assertEqual(api.token, "cached")
        self.assertIsNotNone(api.token_loaded_at)

    def test_stale_but_server_accepted_token_is_not_loaded(self):
        self.write_token(hogart_api.TOKEN_MAX_AGE_SECONDS + 1)
        api = hogart_api.HogartAPI()
        self.assertIsNone(api.token)
        self.assertIsNone(api.token_loaded_at)


if __name__ == "__main__":
    unittest.main()
