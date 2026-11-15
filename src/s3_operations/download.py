import boto3

from src.config import load_config
from src.logging_config import logger


def create_s3_client():
    config = load_config()
    s3_client_args = {
        "aws_access_key_id": config.s3_rawfiles_access_key_id,
        "aws_secret_access_key": config.s3_rawfiles_secret_access_key,
    }
    # Only pass endpoint_url for S3-compatible stores; AWS S3 needs none.
    if config.s3_rawfiles_endpoint:
        s3_client_args["endpoint_url"] = config.s3_rawfiles_endpoint
    return boto3.client("s3", **s3_client_args)


def download_from_s3(key, local_path):
    bucket = load_config().s3_rawfiles_bucket
    try:
        create_s3_client().download_file(bucket, key, local_path)
        logger.info(f"Downloaded {key} to {local_path}")
    except Exception as e:
        logger.error(f"Failed to download {key} from S3: {e}")
        raise


def delete_file_from_s3(key):
    bucket = load_config().s3_rawfiles_bucket
    try:
        create_s3_client().delete_object(Bucket=bucket, Key=key)
        logger.info(f"Deleted {key} from bucket {bucket}")
    except Exception as e:
        logger.error(f"Failed to delete {key} from S3: {e}")
        raise
