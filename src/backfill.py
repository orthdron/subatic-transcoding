"""Bring videos published by the old pipeline up to the current output.

The old pipeline (before the HLS rework) left these in the processed bucket:
5 renditions at <id>/{480p,720p,1080p,1440p,4k}/ with mismatched segment
cuts, short.gif + long.gif card previews, a JPEG sprite with stretched tiles,
and the raw upload itself at <id>/<id>. That raw upload makes a full
re-transcode possible:

- The current pipeline runs on <id>/<id>. Its renditions go under
  <id>/v2/ so no segment URL is ever reused: segments are served as
  immutable, and the old ones (served with no Cache-Control) may still sit in
  viewers' browser caches.
- master.m3u8, sprite.jpg, sprite.vtt and poster.jpg are replaced in place,
  after the old copies are kept under <id>/legacy/ for rollback.
- short.webp and long.mp4 are added; the web app prefers them over the GIFs.

Nothing is deleted by a backfill. Old renditions stay playable for anyone
holding a cached old master.m3u8; `--prune` removes them, the GIFs and the
legacy/ copies once that is no longer a concern. The raw upload at <id>/<id>
is never touched here.

Without --apply every command only prints what it would do.
"""

import argparse
import os
import sys
import time
from collections import defaultdict

from dotenv import load_dotenv

from src.logging_config import logger

RENDITION_ROOT = "v2"
LEGACY_RENDITION_DIRS = {"480p", "720p", "1080p", "1440p", "4k"}
LEGACY_PREVIEWS = ("short.gif", "long.gif")
REPLACED_FILES = ("master.m3u8", "sprite.jpg", "sprite.vtt", "poster.jpg")
LEGACY_BACKUP_DIR = "legacy"
DELETE_BATCH = 1000
# Not the worker's ./upload: cleanup() wipes its whole work root, and a
# backfill must never delete a live worker's job files (or the reverse).
WORK_ROOT = "./backfill-work"


class BucketIndex:
    """Every key in the processed bucket, grouped by video id (first path segment),
    plus each video's master playlist."""

    def __init__(self, keys, masters=None):
        self.videos = defaultdict(set)
        for key in keys:
            video_id, sep, rest = key.partition("/")
            if sep and rest:
                self.videos[video_id].add(rest)
        self.masters = masters or {}

    @classmethod
    def load(cls, client, bucket):
        keys = []
        for page in client.get_paginator("list_objects_v2").paginate(Bucket=bucket):
            keys.extend(obj["Key"] for obj in page.get("Contents", []))
        index = cls(keys)
        for video_id, files in index.videos.items():
            if "master.m3u8" in files:
                body = client.get_object(Bucket=bucket, Key=f"{video_id}/master.m3u8")["Body"]
                index.masters[video_id] = body.read().decode("utf-8", "replace")
        return index

    def files(self, video_id):
        return self.videos.get(video_id, set())

    def has_source(self, video_id):
        return video_id in self.files(video_id)

    def is_backfilled(self, video_id):
        """True once master.m3u8 points only at v2/ renditions.

        Judged by the playlist, not by v2/ files existing: a run that failed
        before uploading the master leaves v2/ files that nothing uses yet.
        """
        lines = self.masters.get(video_id, "").splitlines()
        uris = [line.strip() for line in lines if line.strip() and not line.startswith("#")]
        return bool(uris) and all(uri.startswith(RENDITION_ROOT + "/") for uri in uris)

    def needs_backfill(self, video_id):
        files = self.files(video_id)
        return self.has_source(video_id) and "master.m3u8" in files and not self.is_backfilled(video_id)

    def legacy_leftovers(self, video_id):
        """Files a backfilled video no longer uses (never the raw upload)."""
        if not self.is_backfilled(video_id):
            return []
        leftovers = []
        for f in sorted(self.files(video_id)):
            top = f.split("/", 1)[0]
            if (
                ("/" in f and top in LEGACY_RENDITION_DIRS)
                or top == LEGACY_BACKUP_DIR
                or f in LEGACY_PREVIEWS
            ):
                leftovers.append(f)
        return leftovers


def backfill_video(video_id, client, bucket, index):
    """Re-transcode one legacy video from its raw upload and publish the result."""
    # Imported here so `--help` and planning work without ffmpeg/Pillow installed.
    from src.s3_operations import upload_directory
    from src.video_processing import cleanup, create_adaptive_hls, create_thumbnails, create_workspace, probe_video

    from src.video_processing import workspace as workspace_module

    workspace_module.WORK_ROOT = WORK_ROOT
    started = time.time()
    workspace = create_workspace(video_id)
    try:
        client.download_file(bucket, f"{video_id}/{video_id}", workspace.source)
        info = probe_video(workspace.source)
        create_adaptive_hls(workspace.source, workspace.output, workspace.frames, info, RENDITION_ROOT)
        create_thumbnails(workspace.source, workspace.frames, workspace.output, info)

        published = set(index.files(video_id))
        for name in REPLACED_FILES:
            backup = f"{LEGACY_BACKUP_DIR}/{name}"
            if name in published and backup not in published:
                client.copy_object(
                    Bucket=bucket,
                    Key=f"{video_id}/{backup}",
                    CopySource={"Bucket": bucket, "Key": f"{video_id}/{name}"},
                )

        # Media first and master.m3u8 last, so the switch to v2/ is atomic for players.
        upload_directory(workspace.output, video_id, client)
    finally:
        cleanup()
    logger.info(f"Backfilled {video_id} ({info.duration:.0f}s video) in {time.time() - started:.0f}s")
    return info


def prune_video(video_id, client, bucket, index):
    keys = [f"{video_id}/{f}" for f in index.legacy_leftovers(video_id)]
    for i in range(0, len(keys), DELETE_BATCH):
        batch = keys[i : i + DELETE_BATCH]
        response = client.delete_objects(
            Bucket=bucket, Delete={"Objects": [{"Key": k} for k in batch], "Quiet": True}
        )
        errors = response.get("Errors") or []
        if errors:
            raise RuntimeError(f"Could not delete {len(errors)} legacy files of {video_id}: {errors[:3]}")
    return len(keys)


def select_ids(index, requested, predicate):
    if requested:
        unknown = [v for v in requested if v not in index.videos]
        if unknown:
            raise SystemExit(f"Not in the processed bucket: {', '.join(unknown)}")
        return [v for v in requested if predicate(v)]
    return sorted(v for v in index.videos if predicate(v))


def run(argv=None, client=None):
    parser = argparse.ArgumentParser(prog="backfill.py", description=__doc__.split("\n\n")[0])
    parser.add_argument("ids", nargs="*", help="video ids (default: every eligible video)")
    parser.add_argument("--apply", action="store_true", help="make changes (default: dry run)")
    parser.add_argument("--prune", action="store_true", help="delete legacy files of backfilled videos")
    parser.add_argument("--limit", type=int, help="process at most this many videos")
    parser.add_argument("--env-file", help="load settings from this file instead of .env")
    args = parser.parse_args(argv)

    if args.env_file:
        load_dotenv(args.env_file, override=True)
    else:
        load_dotenv()
    from src.config import load_config
    from src.s3_operations.upload import create_processed_client

    bucket = load_config().s3_processed_bucket
    client = client or create_processed_client()
    index = BucketIndex.load(client, bucket)

    if args.prune:
        ids = select_ids(index, args.ids, lambda v: bool(index.legacy_leftovers(v)))[: args.limit]
        total = 0
        for video_id in ids:
            leftovers = index.legacy_leftovers(video_id)
            print(f"{video_id}: {len(leftovers)} legacy files")
            if args.apply:
                total += prune_video(video_id, client, bucket, index)
        print(f"{'Deleted' if args.apply else 'Would delete'} legacy files of {len(ids)} videos" +
              (f" ({total} objects)" if args.apply else ""))
        return 0

    ids = select_ids(index, args.ids, index.needs_backfill)[: args.limit]
    print(f"{len(ids)} videos to backfill: {' '.join(ids) or '-'}")
    if not args.apply:
        return 0

    failed = []
    for n, video_id in enumerate(ids, 1):
        print(f"[{n}/{len(ids)}] {video_id}", flush=True)
        try:
            backfill_video(video_id, client, bucket, index)
        except Exception:
            logger.exception(f"Backfill failed for {video_id}")
            failed.append(video_id)
    if failed:
        print(f"Failed: {' '.join(failed)}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(run())
