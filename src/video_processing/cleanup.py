import os
import shutil
import glob
from src.logging_config import logger


def cleanup():
    folder_path = "./upload/"
    try:
        remove_files_with_wildcard("./input*")
        shutil.rmtree(folder_path)
        logger.info(f"Folder '{folder_path}' and its contents removed successfully.")
    except FileNotFoundError:
        logger.warning(f"Folder '{folder_path}' not found.")
    except OSError as e:
        logger.error(f"Error occurred while removing folder and its contents: {e}")


def remove_files_with_wildcard(file_pattern):
    files_to_remove = glob.glob(file_pattern)
    for file_path in files_to_remove:
        try:
            os.remove(file_path)
            logger.info(f"File '{file_path}' has been removed.")
        except FileNotFoundError:
            logger.warning(f"File '{file_path}' does not exist.")
        except OSError as e:
            logger.error(f"Error removing file '{file_path}': {e}")
