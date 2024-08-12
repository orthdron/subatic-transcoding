import os
from dotenv import load_dotenv
from src.config import load_config
from src.process import process_webhook_message
from src.sqs_handler import process_sqs_message
import logging
import time


def main():
    load_dotenv()
    config = load_config()

    logger = logging.getLogger(__name__)

    while True:
        try:
            if config.sqs_enabled:
                process_sqs_message(config.sqs_client, config.queue_url)
            else:
                process_webhook_message()
        except Exception as e:
            logger.error(f"Error in main loop: {str(e)}")
        logger.info("Sleeping for 5 seconds...")
        time.sleep(5)


if __name__ == "__main__":
    main()
