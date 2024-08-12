import time
from src.logging_config import logger


def log_time_taken(start):
    end = time.time()
    duration_seconds = end - start
    minutes, seconds = divmod(int(duration_seconds), 60)
    logger.info(f"Time taken: {minutes} minutes and {seconds} seconds")


def setup(file_name):
    from pathlib import Path

    folder_path = f"./upload/{file_name}"
    Path(folder_path).mkdir(parents=True, exist_ok=True)
    logger.info(f"Folder '{folder_path}' created successfully.")


def get_folder_size(folder_path):
    import os

    total_size = 0
    for dirpath, dirnames, filenames in os.walk(folder_path):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            total_size += os.path.getsize(fp)
    return total_size


def calculate_bitrate(folder_size, duration):
    # Convert folder size to bits and duration to seconds
    size_in_bits = folder_size * 8
    bitrate = size_in_bits / duration
    # Convert to kbps and round to nearest 100
    return round(bitrate / 1000 / 100) * 100
