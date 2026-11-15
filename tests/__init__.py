import os

# Tests never talk to real services; give config deterministic values.
os.environ.setdefault("ENABLE_SQS", "false")
os.environ.setdefault("WEBHOOK_URL", "http://web.test/")
os.environ.setdefault("WEBHOOK_TOKEN", "test-token")
os.environ.setdefault("RAWFILES_S3_BUCKET", "raw-bucket")
os.environ.setdefault("PROCESSED_S3_BUCKET", "processed-bucket")
