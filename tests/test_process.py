import unittest
from unittest import mock

from src import process
from src.process import Outcome


class ProcessVideoTest(unittest.TestCase):
    def setUp(self):
        self.patches = {
            name: mock.patch.object(process, name).start()
            for name in ["transcode_and_publish", "send_webhook", "delete_file_from_s3", "cleanup"]
        }
        self.addCleanup(mock.patch.stopall)
        self.patches["transcode_and_publish"].return_value = 42.4

    def test_success_reports_duration_then_deletes_raw(self):
        self.patches["send_webhook"].return_value = True
        self.assertEqual(process.process_video("vid1"), Outcome.DONE)
        self.patches["send_webhook"].assert_called_once_with("vid1", "DONE", 42.4)
        self.patches["delete_file_from_s3"].assert_called_once_with("uploads/vid1")
        self.patches["cleanup"].assert_called_once()

    def test_failed_done_webhook_keeps_raw_upload(self):
        self.patches["send_webhook"].return_value = False
        self.assertEqual(process.process_video("vid1"), Outcome.RETRY)
        self.patches["delete_file_from_s3"].assert_not_called()

    def test_transcode_error_reports_failed(self):
        self.patches["transcode_and_publish"].side_effect = ValueError("broken")
        self.assertEqual(process.process_video("vid1"), Outcome.FAILED)
        self.patches["send_webhook"].assert_called_once_with("vid1", "FAILED")
        self.patches["delete_file_from_s3"].assert_not_called()
        self.patches["cleanup"].assert_called_once()

    def test_raw_delete_failure_still_counts_as_done(self):
        self.patches["send_webhook"].return_value = True
        self.patches["delete_file_from_s3"].side_effect = RuntimeError("s3 down")
        self.assertEqual(process.process_video("vid1"), Outcome.DONE)


class ProcessWebhookMessageTest(unittest.TestCase):
    @mock.patch.object(process, "process_video")
    @mock.patch.object(process, "fetch_next_video", return_value=None)
    def test_idle_when_nothing_queued(self, _fetch, process_video):
        self.assertFalse(process.process_webhook_message())
        process_video.assert_not_called()

    @mock.patch.object(process, "process_video")
    @mock.patch.object(process, "fetch_next_video", return_value="vid1")
    def test_processes_next_video(self, _fetch, process_video):
        self.assertTrue(process.process_webhook_message())
        process_video.assert_called_once_with("vid1")


if __name__ == "__main__":
    unittest.main()
