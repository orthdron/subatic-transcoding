"""Backfill of videos published by the old pipeline, against an in-memory bucket."""

import io
import os
import shutil
import tempfile
import unittest
from unittest import mock

from src import backfill
from src.backfill import BucketIndex
from tests.test_pipeline import HAVE_FFMPEG, assert_card_previews, make_clip

BUCKET = "processed"
LEGACY_MASTER = "#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=3128000,RESOLUTION=1280x720\n720p/stream.m3u8\n"


class FakeBucket:
    """The subset of the boto3 S3 client the backfill uses, backed by a dict."""

    def __init__(self, objects):
        self.objects = dict(objects)

    def get_paginator(self, _name):
        bucket = self

        class Paginator:
            def paginate(self, Bucket):
                yield {"Contents": [{"Key": k} for k in sorted(bucket.objects)]}

        return Paginator()

    def get_object(self, Bucket, Key):
        return {"Body": io.BytesIO(self.objects[Key])}

    def download_file(self, _bucket, key, path):
        with open(path, "wb") as f:
            f.write(self.objects[key])

    def upload_file(self, path, _bucket, key, ExtraArgs=None):
        with open(path, "rb") as f:
            self.objects[key] = f.read()

    def copy_object(self, Bucket, Key, CopySource):
        self.objects[Key] = self.objects[CopySource["Key"]]

    def delete_objects(self, Bucket, Delete):
        for obj in Delete["Objects"]:
            self.objects.pop(obj["Key"], None)
        return {}


def legacy_video(video_id, source=b"raw"):
    files = {
        video_id: source,
        "master.m3u8": LEGACY_MASTER.encode(),
        "720p/stream.m3u8": b"#EXTM3U\n#EXTINF:6.0,\n000.ts\n",
        "720p/000.ts": b"old segment",
        "480p/000.ts": b"old segment",
        "sprite.jpg": b"old sprite",
        "sprite.vtt": b"WEBVTT\n",
        "poster.jpg": b"old poster",
        "short.gif": b"GIF89a",
        "long.gif": b"GIF89a",
    }
    return {f"{video_id}/{name}": data for name, data in files.items()}


class BucketIndexTest(unittest.TestCase):
    def index(self, objects):
        return BucketIndex.load(FakeBucket(objects), BUCKET)

    def test_legacy_video_needs_backfill(self):
        index = self.index(legacy_video("abc"))
        self.assertTrue(index.needs_backfill("abc"))
        self.assertFalse(index.is_backfilled("abc"))
        self.assertEqual(index.legacy_leftovers("abc"), [], "nothing is prunable before the switch")

    def test_video_without_raw_source_is_skipped(self):
        objects = legacy_video("abc")
        del objects["abc/abc"]
        self.assertFalse(self.index(objects).needs_backfill("abc"))

    def test_new_pipeline_video_is_skipped(self):
        objects = {"new/master.m3u8": b"#EXTM3U\n720p/stream.m3u8\n", "new/short.webp": b"x"}
        self.assertFalse(self.index(objects).needs_backfill("new"))

    def test_v2_files_without_switched_master_still_need_backfill(self):
        # A run that died after uploading media but before the master.
        objects = legacy_video("abc")
        objects["abc/v2/720p/000.ts"] = b"new"
        index = self.index(objects)
        self.assertTrue(index.needs_backfill("abc"))
        self.assertEqual(index.legacy_leftovers("abc"), [])

    def test_leftovers_after_switch_keep_raw_source_and_v2(self):
        objects = legacy_video("abc")
        objects["abc/master.m3u8"] = b"#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=1\nv2/720p/stream.m3u8\n"
        objects["abc/v2/720p/000.ts"] = b"new"
        objects["abc/legacy/master.m3u8"] = LEGACY_MASTER.encode()
        index = self.index(objects)
        self.assertFalse(index.needs_backfill("abc"))
        self.assertEqual(
            index.legacy_leftovers("abc"),
            ["480p/000.ts", "720p/000.ts", "720p/stream.m3u8", "legacy/master.m3u8", "long.gif", "short.gif"],
        )


@unittest.skipUnless(HAVE_FFMPEG, "ffmpeg/ffprobe not installed")
class BackfillRunTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        clip = os.path.join(self.tmp, "clip.mp4")
        make_clip(clip, size="1280x720", seconds=8)
        with open(clip, "rb") as f:
            self.bucket = FakeBucket(legacy_video("vid", f.read()))
        self.bucket.objects["other/master.m3u8"] = b"#EXTM3U\n720p/stream.m3u8\n"  # no raw source: untouched
        patches = [
            mock.patch.object(backfill, "WORK_ROOT", os.path.join(self.tmp, "work")),
            # The fake bucket ignores bucket names; upload_directory only needs a value.
            mock.patch("src.s3_operations.upload.load_config"),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def run_backfill(self, *argv):
        with mock.patch("src.config.load_config") as config:
            config.return_value.s3_processed_bucket = BUCKET
            return backfill.run(list(argv), client=self.bucket)

    def test_dry_run_changes_nothing(self):
        before = dict(self.bucket.objects)
        self.assertEqual(self.run_backfill(), 0)
        self.assertEqual(self.run_backfill("--prune"), 0)
        self.assertEqual(self.bucket.objects, before)

    def test_backfill_then_prune(self):
        old = dict(self.bucket.objects)
        self.assertEqual(self.run_backfill("--apply"), 0)
        objects = self.bucket.objects

        master = objects["vid/master.m3u8"].decode()
        uris = [line for line in master.splitlines() if line and not line.startswith("#")]
        self.assertEqual(uris, ["v2/720p/stream.m3u8", "v2/480p/stream.m3u8", "v2/360p/stream.m3u8"])
        for uri in uris:
            self.assertIn(f"vid/{uri}", objects)
            self.assertIn(f"vid/{os.path.dirname(uri)}/000.ts", objects)

        # Old files that viewers may have cached are untouched, and backed up when replaced.
        self.assertEqual(objects["vid/720p/000.ts"], old["vid/720p/000.ts"])
        for name in backfill.REPLACED_FILES:
            self.assertEqual(objects[f"vid/legacy/{name}"], old[f"vid/{name}"])
            self.assertNotEqual(objects[f"vid/{name}"], old[f"vid/{name}"])

        out = os.path.join(self.tmp, "published")
        for name in ("short.webp", "long.mp4"):
            os.makedirs(out, exist_ok=True)
            with open(os.path.join(out, name), "wb") as f:
                f.write(objects[f"vid/{name}"])
        assert_card_previews(self, out, (384, 216))
        self.assertFalse(os.path.exists(backfill.WORK_ROOT), "work folder should be cleaned up")
        self.assertEqual(objects["other/master.m3u8"], old["other/master.m3u8"])

        # A second run finds nothing to do and keeps the first backups.
        self.assertEqual(self.run_backfill("--apply"), 0)
        self.assertEqual(objects["vid/legacy/master.m3u8"], old["vid/master.m3u8"])

        self.assertEqual(self.run_backfill("--prune", "--apply"), 0)
        remaining = sorted(k for k in objects if k.startswith("vid/"))
        self.assertIn("vid/vid", remaining, "the raw upload is never deleted")
        for key in remaining:
            name = key[len("vid/") :]
            self.assertTrue(
                name == "vid" or name.startswith("v2/") or name in (*backfill.REPLACED_FILES, "short.webp", "long.mp4"),
                key,
            )


if __name__ == "__main__":
    unittest.main()
