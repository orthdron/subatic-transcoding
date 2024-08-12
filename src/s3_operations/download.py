import boto3
from src.logging_config import logger
from src.config import load_config

config = load_config()


def download_from_s3(file_name, local_path):
    s3_client = boto3.client(
        "s3",
        aws_access_key_id=config.s3_download_access_key_id,
        aws_secret_access_key=config.s3_download_secret_access_key,
        endpoint_url=config.s3_download_endpoint,
    )
    try:
        s3_client.download_file(
            config.s3_download_bucket, file_name, local_path
        )
        logger.info(f"Downloaded {file_name} to {local_path}")
    except Exception as e:
        logger.error(f"Failed to download {file_name} from S3: {str(e)}")
        raise

def delete_file_from_s3(file_name):
    s3_client = boto3.client(
        "s3",
        aws_access_key_id=config.s3_download_access_key_id,
        aws_secret_access_key=config.s3_download_secret_access_key,
        endpoint_url=config.s3_download_endpoint,
    )
    try:
        s3_client.delete_object(Bucket=config.s3_download_bucket, Key=file_name)
        logger.info(
            f"File {file_name} has been deleted from S3 bucket {config.s3_download_bucket}."
        )
    except Exception as e:
        logger.error(f"Failed to delete file {file_name} from S3: {str(e)}")
        raise
