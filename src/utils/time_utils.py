import time

from src.logging_config import logger


def log_time_taken(start, label="Time taken"):
    minutes, seconds = divmod(int(time.time() - start), 60)
    logger.info(f"{label}: {minutes} minutes and {seconds} seconds")
