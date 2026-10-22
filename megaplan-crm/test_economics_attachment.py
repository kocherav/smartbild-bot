import json
import os
import tempfile
import unittest
from unittest import mock

import deal_browser
from megaplan_api import MegaplanAPIError


class FakeAPI:
    def __init__(self):
        self.calls = []

    def upload_file(self, path):
        return {"id": "new-file", "name": os.path.basename(path)}

    def _call(self, method, path, params=None, json_body=None):
        self.calls.append((method, path, json_body))
        if path == "/comment/old-comment":
            raise AssertionError("Forbidden edit would block the fallback through the shared breaker")
        if path == "/deal/894/comments":
            return {"data": {"id": "new-comment"}}
        if path == "/deal/894/allFiles":
            return {"data": [
                {"id": "old-file", "name": "Экономика сделки №894 — план и факт.xlsx"},
                {"id": "new-file", "name": "Экономика сделки №894 — план и факт.xlsx"},
                {"id": "user-file", "name": "Экономика сделки №894 — план и факт.xlsx"},
            ]}
        if path == "/file/old-file" and method == "DELETE":
            return {"data": "File successfully removed"}
        raise AssertionError(path)


class EconomicsAttachmentTest(unittest.TestCase):
    def test_corrupt_registry_does_not_upload_or_replace_history(self):
        with tempfile.TemporaryDirectory() as folder:
            path=os.path.join(folder,'registry.json')
            with open(path,'w') as file:file.write('{bad')
            with mock.patch.multiple(deal_browser,ECONOMICS_ATTACHMENTS_PATH=path,ECONOMICS_ATTACHMENTS_LOCK=path+'.lock'):
                api=mock.Mock()
                with self.assertRaises(json.JSONDecodeError):deal_browser.replace_economics_attachment(api,'894','file.xlsx')
                api.upload_file.assert_not_called()

    def test_first_create_timeout_does_not_repeat_create(self):
        with tempfile.TemporaryDirectory() as folder:
            path=os.path.join(folder,'registry.json'); api=mock.Mock(); api.upload_file.return_value={'id':'new-file'}
            api._call.side_effect=TimeoutError()
            with mock.patch.multiple(deal_browser,BASE_DIR=folder,ECONOMICS_ATTACHMENTS_PATH=path,ECONOMICS_ATTACHMENTS_LOCK=path+'.lock'):
                with self.assertRaises(TimeoutError):deal_browser.replace_economics_attachment(api,'894','file.xlsx')
                with self.assertRaisesRegex(ValueError,'сверка'):deal_browser.replace_economics_attachment(api,'894','file.xlsx')
            self.assertEqual(1,api._call.call_count); self.assertEqual(1,api.upload_file.call_count)

    def test_new_economics_version_never_edits_forbidden_old_comment(self):
        with tempfile.TemporaryDirectory() as folder:
            workbook = os.path.join(folder, "Экономика сделки №894.xlsx")
            open(workbook, "wb").close()
            registry_path = os.path.join(folder, "registry.json")
            with open(registry_path, "w", encoding="utf-8") as target:
                json.dump({"894": {"comment_id": "old-comment", "file_id": "old-file"}}, target)
            with mock.patch.multiple(deal_browser,
                                     ECONOMICS_ATTACHMENTS_PATH=registry_path,
                                     ECONOMICS_ATTACHMENTS_LOCK=registry_path + ".lock"):
                api = FakeAPI()
                result = deal_browser.replace_economics_attachment(api, "894", workbook)
            self.assertEqual(result["comment_id"], "new-comment")
            self.assertEqual(result["file_id"], "new-file")
            self.assertEqual([call[1] for call in api.calls], [
                "/deal/894/comments", "/deal/894/allFiles",
                "/file/old-file",
            ])


if __name__ == "__main__":
    unittest.main()
