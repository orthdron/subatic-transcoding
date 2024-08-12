import os
from pathlib import Path
from src.logging_config import logger


def setup(file_name):
    folder_path = f"./upload/{file_name}"
    Path(folder_path).mkdir(parents=True, exist_ok=True)
    logger.info(f"Folder '{folder_path}' created successfully.")
    return folder_path
