import time
from venv import logger
from src.s3_operations.download import delete_file_from_s3, download_from_s3
from botocore.exceptions import ClientError
import requests
from src.s3_operations.upload import upload_everything
from src.utils.time_utils import log_time_taken
from src.video_processing import cleanup, setup
from src.video_processing.hls_generator import create_adaptive_hls
from src.video_processing.video_info import is_video_file_fine
from src.webhook import send_webhook

from src.logging_config import logger
from src.config import load_config

config = load_config()


def process_webhook_message():
    if not config.webhook_url or not config.webhook_token:
        logger.error("WEBHOOK_URL or WEBHOOK_TOKEN environment variable is missing")
        return

    endpoint = f"{config.webhook_url.rstrip('/')}/api/video/getNext"
    headers = {"X-Webhook-Token": config.webhook_token}

    try:
        response = requests.get(endpoint, headers=headers)
        response.raise_for_status()
        data = response.json()

        if "id" in data:
            video_id = data["id"]
            try:
                process_video(video_id)
                pass
            except Exception as e:
                logger.error(f"Error processing video: {str(e)}")
                send_webhook(video_id, "FAILED")
        else:
            logger.info("No video to process. Waiting...")
    except requests.RequestException as e:
        logger.error(f"Failed to get next video from webhook: {str(e)}")


def process_video(file_name):
    try:
        setup(file_name)
        raw_file_path = f"./upload/{file_name}/{file_name}"

        download_from_s3(f"uploads/{file_name}", f"./upload/{file_name}/{file_name}")

        if not is_video_file_fine(raw_file_path):
            raise ValueError(f"Broken video: {file_name}")

        start = time.time()
        create_adaptive_hls(raw_file_path, f"./upload/{file_name}")
        logger.info("Adaptive Stream complete")
        log_time_taken(start)

        start = time.time()
        upload_everything()
        logger.info("Upload complete")
        log_time_taken(start)

        send_webhook(file_name, "DONE")

        delete_file_from_s3(f"uploads/{file_name}")
        logger.info(f"File '{file_name}' deleted from main account.")

    except FileNotFoundError as fnf_error:
        logger.error(f"File not found: {fnf_error}")
        send_webhook(file_name, "FAILED")
    except ClientError as client_error:
        logger.error(f"AWS Client error: {client_error}")
        send_webhook(file_name, "FAILED")
    except ValueError as value_error:
        logger.error(f"Value error: {value_error}")
        send_webhook(file_name, "FAILED")
    except Exception as e:
        logger.error(f"Unexpected error in handler: {str(e)}")
        send_webhook(file_name, "FAILED")
    finally:
        cleanup()
