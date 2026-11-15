import unittest
from unittest import mock

import requests

from src import webhook


def response(status):
    r = mock.Mock(status_code=status, ok=200 <= status < 300, text="body")
    return r


class SendWebhookTest(unittest.TestCase):
    def setUp(self):
        self.sleeps = []
        patcher = mock.patch.object(webhook.requests, "post")
        self.post = patcher.start()
        self.addCleanup(patcher.stop)

    def send(self, **kwargs):
        return webhook.send_webhook("vid1", "DONE", 12.6, sleep=self.sleeps.append, **kwargs)

    def test_sends_rounded_integer_duration_with_timeout(self):
        self.post.return_value = response(200)
        self.assertTrue(self.send())
        kwargs = self.post.call_args.kwargs
        self.assertEqual(kwargs["json"], {"id": "vid1", "status": "DONE", "duration": 13})
        self.assertEqual(kwargs["headers"], {"X-Webhook-Token": "test-token"})
        self.assertIsNotNone(kwargs["timeout"])
        self.assertEqual(self.post.call_args.args[0], "http://web.test/api/video/updateStatus")

    def test_retries_transient_failures(self):
        self.post.side_effect = [requests.ConnectionError("down"), response(503), response(200)]
        self.assertTrue(self.send())
        self.assertEqual(self.post.call_count, 3)
        self.assertEqual(len(self.sleeps), 2)

    def test_gives_up_after_all_attempts(self):
        self.post.side_effect = requests.Timeout("slow")
        self.assertFalse(self.send(attempts=3))
        self.assertEqual(self.post.call_count, 3)

    def test_does_not_retry_client_errors(self):
        self.post.return_value = response(400)
        self.assertFalse(self.send())
        self.assertEqual(self.post.call_count, 1)

    def test_retries_rate_limit(self):
        self.post.side_effect = [response(429), response(200)]
        self.assertTrue(self.send())


class FetchNextVideoTest(unittest.TestCase):
    @mock.patch.object(webhook.requests, "get")
    def test_returns_id_and_uses_timeout(self, get):
        get.return_value.json.return_value = {"id": "abc"}
        self.assertEqual(webhook.fetch_next_video(), "abc")
        self.assertIsNotNone(get.call_args.kwargs["timeout"])

    @mock.patch.object(webhook.requests, "get")
    def test_none_when_queue_empty(self, get):
        get.return_value.json.return_value = {"message": "No video requires transcoding"}
        self.assertIsNone(webhook.fetch_next_video())


if __name__ == "__main__":
    unittest.main()
