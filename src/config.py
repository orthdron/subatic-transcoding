import os
import boto3
from dotenv import load_dotenv


class Config:
    def __init__(self):
        self.sqs_enabled = os.getenv("ENABLE_SQS", "false").lower() == "true"
        self.s3_rawfiles_access_key_id = os.getenv("RAWFILES_S3_ACCESS_KEY_ID")
        self.s3_rawfiles_secret_access_key = os.getenv("RAWFILES_S3_SECRET_ACCESS_KEY")
        self.s3_rawfiles_region = os.getenv("RAWFILES_S3_REGION")
        self.s3_rawfiles_endpoint = os.getenv("RAWFILES_S3_ENDPOINT")
        self.s3_rawfiles_bucket = os.getenv("RAWFILES_S3_BUCKET")

        self.s3_processed_access_key_id = os.getenv("PROCESSED_S3_ACCESS_KEY_ID")
        self.s3_processed_secret_access_key = os.getenv("PROCESSED_S3_SECRET_ACCESS_KEY")
        self.s3_processed_region = os.getenv("PROCESSED_S3_REGION", "auto")
        self.s3_processed_endpoint = os.getenv("PROCESSED_S3_ENDPOINT")
        self.s3_processed_bucket = os.getenv("PROCESSED_S3_BUCKET")

        self.aws_sqs_url = os.getenv("SQS_URL")

        self.webhook_url = os.getenv("WEBHOOK_URL")
        self.webhook_token = os.getenv("WEBHOOK_TOKEN")

        if self.sqs_enabled:
            self.sqs_client = self._create_sqs_client()
            self.queue_url = self.aws_sqs_url

    def _create_sqs_client(self):
        return boto3.Session(
            aws_access_key_id=self.s3_rawfiles_access_key_id,
            aws_secret_access_key=self.s3_rawfiles_secret_access_key,
            region_name=self.s3_rawfiles_region,
            endpoint_url=self.s3_rawfiles_endpoint,
        ).client("sqs")


def load_config():
    load_dotenv()
    return Config()
