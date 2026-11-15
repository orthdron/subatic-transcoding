"""Delete videos that are past the retention policy: files first, then the database row.

The web app decides which videos have expired (GET /api/video/expired) and
deletes their rows (POST /api/video/delete, which re-checks the policy).
This worker holds the bucket credentials, so it deletes the files in between:
everything under <id>/ in the processed bucket and uploads/<id> in the raw
bucket. Files go first so a failure never leaves public files without a row
pointing at them; the next run retries the video.

Meant for cron, e.g. daily on the host running the worker:

    python -m src.retention --older-than-days 30 --keep-user admin --apply

Without --apply it only lists what it would delete.
"""

import argparse
import re
import sys

import requests
from dotenv import load_dotenv

from src.logging_config import logger

VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]+$")


def fetch_expired(policy, session=requests):
    from src.webhook import REQUEST_TIMEOUT, _endpoint

    url, headers = _endpoint("/api/video/expired")
    params = {"olderThanDays": policy["olderThanDays"], "keepUser": policy["keepUsers"]}
    response = session.get(url, params=params, headers=headers, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    return response.json()["ids"]


def delete_row(video_id, policy, session=requests):
    from src.webhook import REQUEST_TIMEOUT, _endpoint

    url, headers = _endpoint("/api/video/delete")
    response = session.post(url, json={"id": video_id, **policy}, headers=headers, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    return response.json()["deleted"]


def delete_files(video_id, processed, processed_bucket, raw, raw_bucket):
    """Delete every processed file of the video and its raw upload. Returns the number of objects."""
    from src.backfill import delete_keys

    if not VIDEO_ID.match(video_id):
        # An empty or odd id must never turn into a bucket-wide prefix.
        raise ValueError(f"Refusing to delete files for video id {video_id!r}")
    keys = []
    for page in processed.get_paginator("list_objects_v2").paginate(Bucket=processed_bucket, Prefix=f"{video_id}/"):
        keys.extend(obj["Key"] for obj in page.get("Contents", []))
    delete_keys(video_id, processed, processed_bucket, keys)
    # Normally already gone after transcoding; deleting a missing key is a no-op.
    raw.delete_object(Bucket=raw_bucket, Key=f"uploads/{video_id}")
    return len(keys)


def run(argv=None, processed=None, raw=None, session=requests):
    parser = argparse.ArgumentParser(prog="python -m src.retention", description=__doc__.split("\n\n")[0])
    parser.add_argument("--older-than-days", type=int, required=True, help="delete videos uploaded before this many days ago")
    parser.add_argument("--keep-user", action="append", required=True, help="user whose videos are never deleted (repeatable)")
    parser.add_argument("--apply", action="store_true", help="delete (default: only list)")
    parser.add_argument("--env-file", help="load settings from this file instead of .env")
    args = parser.parse_args(argv)
    if args.older_than_days < 0:
        parser.error("--older-than-days must be 0 or more")

    if args.env_file:
        load_dotenv(args.env_file, override=True)
    else:
        load_dotenv()
    from src.config import load_config
    from src.s3_operations.download import create_s3_client
    from src.s3_operations.upload import create_processed_client

    config = load_config()
    policy = {"olderThanDays": args.older_than_days, "keepUsers": args.keep_user}
    ids = fetch_expired(policy, session)
    print(
        f"{len(ids)} videos older than {args.older_than_days} days not by {', '.join(args.keep_user)}: "
        f"{' '.join(ids) or '-'}",
        flush=True,
    )
    if not args.apply:
        return 0

    processed = processed or create_processed_client()
    raw = raw or create_s3_client()
    failed = []
    for video_id in ids:
        try:
            count = delete_files(video_id, processed, config.s3_processed_bucket, raw, config.s3_rawfiles_bucket)
            deleted = delete_row(video_id, policy, session)
            logger.info(f"Deleted video {video_id}: {count} files, row {'deleted' if deleted else 'already gone'}")
        except Exception:
            logger.exception(f"Could not delete video {video_id}")
            failed.append(video_id)
    if failed:
        print(f"Failed: {' '.join(failed)}")
        return 1
    print(f"Deleted {len(ids)} videos")
    return 0


if __name__ == "__main__":
    sys.exit(run())
