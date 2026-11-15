import os
from concurrent.futures import ThreadPoolExecutor

import boto3

from src.config import load_config
from src.logging_config import logger

CONTENT_TYPES = {
    ".m3u8": "application/vnd.apple.mpegurl",
    ".ts": "video/mp2t",
    ".vtt": "text/vtt",
    ".jpg": "image/jpeg",
    ".gif": "image/gif",
}
# Segment names are reused only if the whole video is re-transcoded, which
# happens before it is ever marked DONE, so segments can be cached forever.
SEGMENT_CACHE_CONTROL = "public, max-age=31536000, immutable"
DEFAULT_CACHE_CONTROL = "public, max-age=86400"

UPLOAD_WORKERS = 10


def create_processed_client():
    config = load_config()
    return boto3.client(
        "s3",
        aws_access_key_id=config.s3_processed_access_key_id,
        aws_secret_access_key=config.s3_processed_secret_access_key,
        endpoint_url=config.s3_processed_endpoint,
        region_name=config.s3_processed_region,
    )


def upload_args(path):
    ext = os.path.splitext(path)[1].lower()
    return {
        "ContentType": CONTENT_TYPES.get(ext, "application/octet-stream"),
        "CacheControl": SEGMENT_CACHE_CONTROL if ext == ".ts" else DEFAULT_CACHE_CONTROL,
    }


def plan_upload(output_dir, video_id):
    """Group files into ordered batches: media, then rendition playlists, then master.m3u8.

    Uploading in this order means a playlist that is already visible never
    points at a segment that is not there yet.
    """
    media, playlists, master = [], [], []
    for root, _dirs, files in os.walk(output_dir):
        for name in sorted(files):
            local_path = os.path.join(root, name)
            key = f"{video_id}/{os.path.relpath(local_path, output_dir)}".replace(os.sep, "/")
            if key == f"{video_id}/master.m3u8":
                master.append((local_path, key))
            elif name.endswith(".m3u8"):
                playlists.append((local_path, key))
            else:
                media.append((local_path, key))
    return [batch for batch in (media, playlists, master) if batch]


def upload_directory(output_dir, video_id, s3_client=None):
    client = s3_client or create_processed_client()
    bucket = load_config().s3_processed_bucket
    batches = plan_upload(output_dir, video_id)
    total = sum(len(batch) for batch in batches)
    logger.info(f"Uploading {total} files to {bucket}/{video_id}/")

    with ThreadPoolExecutor(max_workers=UPLOAD_WORKERS) as executor:
        for batch in batches:
            futures = {
                executor.submit(
                    client.upload_file, local_path, bucket, key, ExtraArgs=upload_args(local_path)
                ): key
                for local_path, key in batch
            }
            for future, key in futures.items():
                try:
                    future.result()
                except Exception as e:
                    raise RuntimeError(f"Failed to upload {key}: {e}") from e
