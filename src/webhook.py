import requests
from src.logging_config import logger
from src.config import load_config


config = load_config()


def send_webhook(video_id, status, duration=0):
    if not config.webhook_url or not config.webhook_token:
        logger.error("WEBHOOK_URL or WEBHOOK_TOKEN environment variable is missing")
        return

    webhook_url = config.webhook_url.rstrip("/") + "/api/video/updateStatus"

    payload = {"id": video_id, "status": status, "duration": duration}
    headers = {"X-Webhook-Token": config.webhook_token}

    try:
        response = requests.post(webhook_url, json=payload, headers=headers)
        response.raise_for_status()
        logger.info(
            f"Webhook sent successfully for video {video_id} with status {status} and duration {duration}"
        )
    except requests.RequestException as e:
        logger.error(f"Failed to send webhook for video {video_id}: {str(e)}")
