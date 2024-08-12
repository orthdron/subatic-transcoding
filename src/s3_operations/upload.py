from concurrent.futures import ThreadPoolExecutor
import os
import boto3
from src.logging_config import logger
from src.config import load_config

config = load_config()


def upload_to_s3(local_path, relative_path, s3_client):
    try:
        s3_client.upload_file(local_path, config.s3_upload_bucket, relative_path)
    except Exception as e:
        logger.error(f"Failed to upload {local_path} to S3. Error: {str(e)}")
        raise
    
def upload_everything():
    s3_client = boto3.client(
        "s3",
        aws_access_key_id=config.s3_upload_access_key_id,
        aws_secret_access_key=config.s3_upload_secret_access_key,
        endpoint_url=config.s3_upload_endpoint,
        region_name=config.s3_upload_region
    )

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = []
        for root, dirs, files in os.walk("./upload"):
            for file in files:
                local_path = os.path.join(root, file)
                relative_path = os.path.relpath(local_path, "./upload")
                future = executor.submit(
                    upload_to_s3, local_path, relative_path, s3_client
                )
                futures.append(future)

        for future in futures:
            try:
                future.result()
            except Exception as e:
                logger.error(f"Error in upload_everything: {str(e)}")
                raise  # Re-raise the exception to trigger the FAILED webhook