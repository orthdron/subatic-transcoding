import json
import os
import threading
from urllib.parse import unquote_plus

from src.logging_config import logger
from src.process import Outcome, process_video

UPLOAD_EVENTS = {"ObjectCreated:Put", "ObjectCreated:CompleteMultipartUpload"}
# A received message stays hidden from other workers this long; the heartbeat
# keeps pushing it out while the job runs, so a long transcode is never handed
# to a second worker, while a crashed worker's job reappears within minutes.
VISIBILITY_TIMEOUT = 300
HEARTBEAT_INTERVAL = 120


def process_sqs_message(sqs_client, queue_url):
    """Long-poll for one S3 event message and process the uploads it names.

    Receive errors propagate so the main loop can back off.
    """
    response = sqs_client.receive_message(
        QueueUrl=queue_url,
        MaxNumberOfMessages=1,
        WaitTimeSeconds=20,
        VisibilityTimeout=VISIBILITY_TIMEOUT,
    )
    messages = response.get("Messages", [])
    if not messages:
        logger.info("No messages in the queue.")
        return

    message = messages[0]
    receipt_handle = message["ReceiptHandle"]
    body = message.get("Body")
    logger.info(f"Received message: {body}")

    outcomes = []
    with VisibilityHeartbeat(sqs_client, queue_url, receipt_handle):
        for key in extract_object_keys(body):
            outcomes.append(process_video(os.path.basename(key)))

    if Outcome.RETRY in outcomes:
        logger.warning("Leaving the message on the queue so the job is retried after the visibility timeout")
        return

    sqs_client.delete_message(QueueUrl=queue_url, ReceiptHandle=receipt_handle)


def extract_object_keys(body):
    """Object keys of upload events in an S3 notification body.

    S3 URL-encodes keys in notifications (a space arrives as '+').
    """
    if not body:
        logger.warning("Received empty message body")
        return []
    try:
        records = json.loads(body).get("Records", [])
    except (json.JSONDecodeError, AttributeError):
        logger.warning("Message body is not an S3 event notification; dropping it")
        return []

    keys = []
    for record in records:
        if record.get("eventName") not in UPLOAD_EVENTS:
            continue
        key = record.get("s3", {}).get("object", {}).get("key")
        if key:
            keys.append(unquote_plus(key))
        else:
            logger.warning(f"Upload event without an object key: {record}")
    return keys


class VisibilityHeartbeat:
    """Keep an in-flight SQS message hidden for as long as the block runs."""

    def __init__(self, client, queue_url, receipt_handle, timeout=VISIBILITY_TIMEOUT, interval=HEARTBEAT_INTERVAL):
        self.client = client
        self.queue_url = queue_url
        self.receipt_handle = receipt_handle
        self.timeout = timeout
        self.interval = interval
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="sqs-heartbeat", daemon=True)

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *exc_info):
        self._stop.set()
        self._thread.join()

    def _run(self):
        while not self._stop.wait(self.interval):
            try:
                self.client.change_message_visibility(
                    QueueUrl=self.queue_url,
                    ReceiptHandle=self.receipt_handle,
                    VisibilityTimeout=self.timeout,
                )
            except Exception as e:
                logger.warning(f"Could not extend SQS message visibility: {e}")
