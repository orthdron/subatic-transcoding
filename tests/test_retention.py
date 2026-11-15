"""Retention: files of expired videos are deleted from both buckets before their rows."""

import unittest
from unittest import mock

from src import retention
from tests.test_backfill import FakeBucket


class RawBucket(FakeBucket):
    def delete_object(self, Bucket, Key):
        self.objects.pop(Key, None)


class FakeWebApp:
    """Stands in for requests against the web app's retention endpoints."""

    POLICY = {"olderThanDays": 30, "keepUsers": ["admin"]}

    def __init__(self, expired, processed):
        self.expired = list(expired)
        self.processed = processed
        self.calls = []
        self.enabled = True

    def get(self, url, headers, timeout):
        self.calls.append(("list", url, None))
        if not self.enabled:
            return mock.Mock(status_code=404)
        ids = list(self.expired)
        return mock.Mock(status_code=200, json=lambda: {"ids": ids, "policy": self.POLICY}, raise_for_status=lambda: None)

    def post(self, url, json, headers, timeout):
        video_id = json["id"]
        # The row may only go once its files are gone.
        assert not any(k.startswith(f"{video_id}/") for k in self.processed.objects), "files must go first"
        self.calls.append(("delete", url, json))
        deleted = video_id in self.expired
        self.expired = [v for v in self.expired if v != video_id]
        return mock.Mock(json=lambda: {"deleted": deleted}, raise_for_status=lambda: None)


class RetentionTest(unittest.TestCase):
    def setUp(self):
        self.processed = FakeBucket(
            {
                "old/master.m3u8": b"",
                "old/v2/720p/000.ts": b"",
                "old/old": b"raw",
                "older/master.m3u8": b"",
                "kept/master.m3u8": b"",
                "oldest/master.m3u8": b"",  # 'old' must not match this prefix
            }
        )
        self.raw = RawBucket({"uploads/old": b"raw", "uploads/kept": b"raw"})
        self.web = FakeWebApp(["old", "older"], self.processed)
        config = mock.Mock(s3_processed_bucket="processed", s3_rawfiles_bucket="raw")
        for p in (
            mock.patch("src.config.load_config", return_value=config),
            mock.patch("src.webhook._endpoint", side_effect=lambda path: (f"https://web{path}", {"X-Webhook-Token": "t"})),
        ):
            p.start()
            self.addCleanup(p.stop)

    def run_retention(self, *argv):
        return retention.run(
            list(argv),
            processed=self.processed,
            raw=self.raw,
            session=self.web,
        )

    def test_dry_run_only_lists(self):
        before = (dict(self.processed.objects), dict(self.raw.objects))
        self.assertEqual(self.run_retention(), 0)
        self.assertEqual((self.processed.objects, self.raw.objects), before)
        self.assertEqual(self.web.calls, [("list", "https://web/api/video/expired", None)])

    def test_apply_deletes_files_then_rows(self):
        self.assertEqual(self.run_retention("--apply"), 0)
        self.assertEqual(sorted(self.processed.objects), ["kept/master.m3u8", "oldest/master.m3u8"])
        self.assertEqual(sorted(self.raw.objects), ["uploads/kept"])
        deletes = [c[2] for c in self.web.calls if c[0] == "delete"]
        # Only the id is sent: the policy lives in the web app and cannot be widened from here.
        self.assertEqual(deletes, [{"id": "old"}, {"id": "older"}])

    def test_odd_id_is_refused_and_reported(self):
        self.web.expired = ["", "old"]
        self.assertEqual(self.run_retention("--apply"), 1)
        self.assertIn("kept/master.m3u8", self.processed.objects)
        self.assertNotIn("old/master.m3u8", self.processed.objects, "other videos still processed")

    def test_retention_off_on_the_web_app_deletes_nothing(self):
        self.web.enabled = False
        before = dict(self.processed.objects)
        self.assertEqual(self.run_retention("--apply"), 1)
        self.assertEqual(self.processed.objects, before)
        self.assertEqual([c[0] for c in self.web.calls], ["list"])


if __name__ == "__main__":
    unittest.main()
