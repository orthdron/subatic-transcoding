import time

from dotenv import load_dotenv

from src.config import load_config
from src.logging_config import logger
from src.process import process_webhook_message
from src.sqs_handler import process_sqs_message
from src.video_processing import cleanup

IDLE_POLL_SECONDS = 5
MAX_BACKOFF_SECONDS = 60


def main():
    load_dotenv()
    config = load_config()
    cleanup()  # leftovers from a run that crashed mid-job

    failures = 0
    while True:
        delay = 0
        try:
            if config.sqs_enabled:
                # Long-polls for up to 20 s itself, so no extra sleep.
                process_sqs_message(config.sqs_client, config.queue_url)
            elif not process_webhook_message():
                delay = IDLE_POLL_SECONDS
            failures = 0
        except Exception:
            failures += 1
            delay = min(MAX_BACKOFF_SECONDS, IDLE_POLL_SECONDS * 2 ** (failures - 1))
            logger.exception(f"Error in main loop; retrying in {delay}s")
        if delay:
            time.sleep(delay)


if __name__ == "__main__":
    main()
