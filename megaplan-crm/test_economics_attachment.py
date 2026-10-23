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


class UnchangedEconomicsTest(unittest.TestCase):
    """QA 23.10: the read button rewrote the CRM file three times."""

    def publish(self, folder, registry, fingerprint, files):
        workbook = os.path.join(folder, "Экономика сделки №894 — план и факт.xlsx")
        open(workbook, "wb").close()
        path = os.path.join(folder, "registry.json")
        with open(path, "w", encoding="utf-8") as target:
            json.dump(registry, target)
        api = mock.Mock()
        api.upload_file.return_value = {"id": "new-file", "name": os.path.basename(workbook)}
        def call(method, url, params=None, json_body=None):
            if url.endswith("/allFiles"):
                return {"data": files + ([{"id": "new-file"}] if api.upload_file.called else [])}
            if url.endswith("/comments"):
                return {"data": {"id": "new-comment"}}
            return {"data": {}}
        api._call.side_effect = call
        with mock.patch.multiple(deal_browser, ECONOMICS_ATTACHMENTS_PATH=path, ECONOMICS_ATTACHMENTS_LOCK=path + ".lock"):
            result = deal_browser.replace_economics_attachment(api, "894", workbook, fingerprint)
        with open(path, encoding="utf-8") as source:
            return result, api, json.load(source)

    def test_same_numbers_and_file_present_write_nothing(self):
        with tempfile.TemporaryDirectory() as folder:
            result, api, _ = self.publish(folder, {"894": {"comment_id": "c", "file_id": "old-file",
                                                          "data_fingerprint": "abc"}}, "abc", [{"id": "old-file"}])
        self.assertTrue(result["unchanged"])
        api.upload_file.assert_not_called()
        self.assertEqual([("GET", "/deal/894/allFiles")], [c.args[:2] for c in api._call.call_args_list])

    def test_changed_numbers_publish_and_remember_the_new_fingerprint(self):
        with tempfile.TemporaryDirectory() as folder:
            result, api, registry = self.publish(folder, {"894": {"comment_id": "c", "file_id": "old-file",
                                                                 "data_fingerprint": "abc"}}, "def", [{"id": "old-file"}])
        self.assertNotIn("unchanged", result)
        api.upload_file.assert_called_once()
        self.assertEqual("def", registry["894"]["data_fingerprint"])

    def test_missing_published_file_or_unknown_fingerprint_is_republished(self):
        with tempfile.TemporaryDirectory() as folder:
            _result, api, _ = self.publish(folder, {"894": {"comment_id": "c", "file_id": "old-file",
                                                           "data_fingerprint": "abc"}}, "abc", [])
            api.upload_file.assert_called_once()
        with tempfile.TemporaryDirectory() as folder:
            _result, api, registry = self.publish(folder, {"894": {"comment_id": "c", "file_id": "old-file"}},
                                                  "abc", [{"id": "old-file"}])
            api.upload_file.assert_called_once()
            self.assertEqual("abc", registry["894"]["data_fingerprint"])


class ProfitabilityFingerprintTest(unittest.TestCase):
    def test_fingerprint_follows_numbers_not_build_time(self):
        import build_profitability_report as report
        rows = [{"name": "Сплит", "qty": 2, "revenue": 90000.0}]
        totals = {"revenue": 90000.0, "cost": 60000.0, "profit": 30000.0, "margin": 33.3}
        first = report.data_fingerprint("894", rows, totals, [])
        self.assertEqual(first, report.data_fingerprint("894", [dict(rows[0])], dict(totals), []))
        self.assertNotEqual(first, report.data_fingerprint("894", [{**rows[0], "qty": 3}], totals, []))
        self.assertNotEqual(first, report.data_fingerprint("895", rows, totals, []))


if __name__ == "__main__":
    unittest.main()
