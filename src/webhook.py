import time

import requests

from src.config import load_config
from src.logging_config import logger

# (connect, read) seconds. Without a timeout a hung web server would block
# the worker forever.
REQUEST_TIMEOUT = (5, 30)
WEBHOOK_ATTEMPTS = 6
MAX_RETRY_DELAY = 30


class WebhookNotConfigured(RuntimeError):
    pass


def _endpoint(path):
    config = load_config()
    if not config.webhook_url or not config.webhook_token:
        raise WebhookNotConfigured("WEBHOOK_URL or WEBHOOK_TOKEN environment variable is missing")
    return config.webhook_url.rstrip("/") + path, {"X-Webhook-Token": config.webhook_token}


def fetch_next_video():
    """Ask the web app for the next video to transcode. Returns its id or None."""
    url, headers = _endpoint("/api/video/getNext")
    response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    return response.json().get("id")


def send_webhook(video_id, status, duration=0, attempts=WEBHOOK_ATTEMPTS, sleep=time.sleep):
    """Report a job result to the web app, retrying transient failures.

    Returns True once the web app accepted the update. Network errors, 5xx and
    429 are retried with backoff (about a minute in total); other 4xx answers
    mean retrying cannot help, so they fail at once.
    """
    try:
        url, headers = _endpoint("/api/video/updateStatus")
    except WebhookNotConfigured as e:
        logger.error(str(e))
        return False

    # The web app stores duration in an integer column.
    payload = {"id": video_id, "status": status, "duration": int(round(duration))}

    for attempt in range(1, attempts + 1):
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=REQUEST_TIMEOUT)
        except requests.RequestException as e:
            error, retryable = str(e), True
        else:
            if response.ok:
                logger.info(f"Webhook sent for video {video_id}: {status}, duration {payload['duration']}s")
                return True
            error = f"HTTP {response.status_code}: {response.text[:200]}"
            retryable = response.status_code >= 500 or response.status_code == 429

        if not retryable or attempt == attempts:
            logger.error(f"Webhook for video {video_id} ({status}) failed after {attempt} attempt(s): {error}")
            return False

        delay = min(MAX_RETRY_DELAY, 2**attempt)
        logger.warning(f"Webhook for video {video_id} failed ({error}); retrying in {delay}s")
        sleep(delay)
    return False
