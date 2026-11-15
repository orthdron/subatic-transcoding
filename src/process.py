import time
from enum import Enum

from src.logging_config import logger
from src.s3_operations import delete_file_from_s3, download_from_s3, upload_directory
from src.utils.time_utils import log_time_taken
from src.video_processing import (
    cleanup,
    create_adaptive_hls,
    create_thumbnails,
    create_workspace,
    probe_video,
)
from src.webhook import fetch_next_video, send_webhook


class Outcome(Enum):
    DONE = "done"  # published, web app notified, raw upload deleted
    FAILED = "failed"  # could not be transcoded; FAILED reported
    RETRY = "retry"  # published, but the web app was not told; raw upload kept


def process_webhook_message():
    """Fetch and process one video. Returns False when there was nothing to do."""
    video_id = fetch_next_video()
    if not video_id:
        logger.info("No video to process.")
        return False
    process_video(video_id)
    return True


def process_video(video_id):
    started = time.time()
    try:
        duration = transcode_and_publish(video_id)
    except Exception:
        logger.exception(f"Processing failed for video {video_id}")
        send_webhook(video_id, "FAILED")
        return Outcome.FAILED
    finally:
        cleanup()

    if not send_webhook(video_id, "DONE", duration):
        # Keep the raw upload: once the web app's MARK_FAILED_AFTER timeout
        # (or the SQS visibility timeout) puts the job back in the queue, it
        # can be transcoded again instead of failing on a missing source.
        logger.error(f"Video {video_id} is published but its DONE status was not recorded; raw upload kept")
        return Outcome.RETRY

    try:
        delete_file_from_s3(f"uploads/{video_id}")
    except Exception:
        # The video is live and recorded as DONE; a leftover raw file only costs storage.
        logger.exception(f"Could not delete raw upload for video {video_id}")

    logger.info(f"Video {video_id} done")
    log_time_taken(started)
    return Outcome.DONE


def transcode_and_publish(video_id):
    """Download, transcode, and upload one video. Returns its duration in seconds."""
    workspace = create_workspace(video_id)

    start = time.time()
    download_from_s3(f"uploads/{video_id}", workspace.source)
    log_time_taken(start, "Download")

    info = probe_video(workspace.source)

    start = time.time()
    create_adaptive_hls(workspace.source, workspace.output, workspace.frames, info)
    create_thumbnails(workspace.source, workspace.frames, workspace.output, info)
    log_time_taken(start, "Transcode")

    start = time.time()
    upload_directory(workspace.output, video_id)
    log_time_taken(start, "Upload")

    return info.duration
