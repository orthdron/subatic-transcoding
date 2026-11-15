import json
import threading
import unittest
from unittest import mock

from src import sqs_handler
from src.process import Outcome


def s3_event(*keys, event="ObjectCreated:Put"):
    return json.dumps({"Records": [{"eventName": event, "s3": {"object": {"key": k}}} for k in keys]})


class ExtractObjectKeysTest(unittest.TestCase):
    def test_decodes_url_encoded_keys(self):
        self.assertEqual(sqs_handler.extract_object_keys(s3_event("uploads/my+video%281%29")), ["uploads/my video(1)"])

    def test_ignores_other_events_and_garbage(self):
        self.assertEqual(sqs_handler.extract_object_keys(s3_event("uploads/a", event="ObjectRemoved:Delete")), [])
        self.assertEqual(sqs_handler.extract_object_keys("not json"), [])
        self.assertEqual(sqs_handler.extract_object_keys(json.dumps({"Event": "s3:TestEvent"})), [])


class ProcessSqsMessageTest(unittest.TestCase):
    def setUp(self):
        self.client = mock.Mock()
        self.client.receive_message.return_value = {
            "Messages": [{"ReceiptHandle": "rh", "Body": s3_event("uploads/vid1")}]
        }

    @mock.patch.object(sqs_handler, "process_video", return_value=Outcome.DONE)
    def test_processes_and_deletes(self, process_video):
        sqs_handler.process_sqs_message(self.client, "queue")
        process_video.assert_called_once_with("vid1")
        self.client.delete_message.assert_called_once_with(QueueUrl="queue", ReceiptHandle="rh")
        self.assertEqual(self.client.receive_message.call_args.kwargs["VisibilityTimeout"], sqs_handler.VISIBILITY_TIMEOUT)

    @mock.patch.object(sqs_handler, "process_video", return_value=Outcome.FAILED)
    def test_failed_jobs_are_not_redelivered(self, _process_video):
        sqs_handler.process_sqs_message(self.client, "queue")
        self.client.delete_message.assert_called_once()

    @mock.patch.object(sqs_handler, "process_video", return_value=Outcome.RETRY)
    def test_retry_leaves_message_on_queue(self, _process_video):
        sqs_handler.process_sqs_message(self.client, "queue")
        self.client.delete_message.assert_not_called()


class VisibilityHeartbeatTest(unittest.TestCase):
    def test_extends_visibility_while_running(self):
        client = mock.Mock()
        extended = threading.Event()
        client.change_message_visibility.side_effect = lambda **_: extended.set()
        with sqs_handler.VisibilityHeartbeat(client, "queue", "rh", timeout=300, interval=0.01):
            self.assertTrue(extended.wait(2))
        client.change_message_visibility.assert_called_with(QueueUrl="queue", ReceiptHandle="rh", VisibilityTimeout=300)

    def test_survives_api_errors(self):
        client = mock.Mock()
        client.change_message_visibility.side_effect = RuntimeError("throttled")
        with sqs_handler.VisibilityHeartbeat(client, "queue", "rh", interval=0.01):
            threading.Event().wait(0.05)
        self.assertGreater(client.change_message_visibility.call_count, 1)


if __name__ == "__main__":
    unittest.main()
