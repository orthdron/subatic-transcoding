"""End-to-end runs of the real ffmpeg pipeline on generated clips (S3 and webhook stubbed)."""

import os
import re
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

from src import process
from src.video_processing import workspace as workspace_module
from src.video_processing.ffmpeg_cli import probe_stream
from src.video_processing.hls_generator import read_media_playlist

HAVE_FFMPEG = shutil.which("ffmpeg") and shutil.which("ffprobe")


def make_clip(path, size, seconds, audio=True, extra_input_args=()):
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"testsrc2=size={size}:rate=30"]
    if audio:
        cmd += ["-f", "lavfi", "-i", "sine=f=440:sample_rate=44100"]
    cmd += ["-t", str(seconds), "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p"]
    cmd += ["-c:a", "aac"] if audio else []
    cmd.append(path)
    subprocess.run(cmd, check=True)
    if extra_input_args:
        rotated = path + ".tmp.mp4"
        subprocess.run(["ffmpeg", "-v", "error", "-y", *extra_input_args, "-i", path, "-c", "copy", rotated], check=True)
        os.replace(rotated, path)


class FakeS3:
    """Stands in for both buckets: serves local raw files, records uploads."""

    def __init__(self, raw_files, published_dir):
        self.raw_files = raw_files
        self.published_dir = published_dir
        self.extra_args = {}

    def download(self, key, local_path):
        shutil.copy(self.raw_files[key], local_path)

    def upload_file(self, local_path, _bucket, key, ExtraArgs):
        target = os.path.join(self.published_dir, key)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copy(local_path, target)
        self.extra_args[key] = ExtraArgs


@unittest.skipUnless(HAVE_FFMPEG, "ffmpeg/ffprobe not installed")
class PipelineTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.clips = {
            "landscape": (os.path.join(cls.tmp, "landscape.mp4"), dict(size="1280x720", seconds=14)),
            "phone": (
                os.path.join(cls.tmp, "phone.mp4"),
                # Stored as landscape with a 90 degree display rotation, like phone footage.
                dict(size="1280x720", seconds=4, extra_input_args=("-display_rotation", "90")),
            ),
            "tiny": (os.path.join(cls.tmp, "tiny.mp4"), dict(size="320x240", seconds=3, audio=False)),
            "blip": (os.path.join(cls.tmp, "blip.mp4"), dict(size="640x360", seconds=1)),
        }
        for path, options in cls.clips.values():
            make_clip(path, **options)

    def run_pipeline(self, name):
        published = os.path.join(self.tmp, "published", name)
        work_root = os.path.join(self.tmp, "work", name)
        s3 = FakeS3({f"uploads/{name}": self.clips[name][0]}, published)
        with mock.patch.object(workspace_module, "WORK_ROOT", work_root), \
             mock.patch.object(process, "download_from_s3", s3.download), \
             mock.patch("src.s3_operations.upload.create_processed_client", return_value=s3), \
             mock.patch.object(process, "send_webhook", return_value=True) as webhook, \
             mock.patch.object(process, "delete_file_from_s3") as delete_raw:
            outcome = process.process_video(name)
        self.assertEqual(outcome, process.Outcome.DONE)
        self.assertFalse(os.path.exists(work_root), "workspace should be cleaned up")
        delete_raw.assert_called_once_with(f"uploads/{name}")
        return os.path.join(published, name), webhook, s3

    def master_entries(self, out):
        with open(os.path.join(out, "master.m3u8")) as f:
            text = f.read()
        entries = re.findall(r"#EXT-X-STREAM-INF:(.*)\n(.*)", text)
        return [(dict(re.findall(r'([A-Z-]+)=("[^"]*"|[^,]*)', attrs)), uri) for attrs, uri in entries]

    def assert_common_outputs(self, out):
        for name in ["master.m3u8", "sprite.jpg", "sprite.vtt", "short.gif", "long.gif", "poster.jpg"]:
            self.assertTrue(os.path.exists(os.path.join(out, name)), name)
        self.assertFalse(os.path.exists(os.path.join(out, os.path.basename(out))), "raw source must not be published")

    def test_landscape(self):
        out, webhook, s3 = self.run_pipeline("landscape")
        self.assert_common_outputs(out)
        webhook.assert_called_once_with("landscape", "DONE", mock.ANY)
        self.assertAlmostEqual(webhook.call_args.args[2], 14, delta=0.2)

        entries = self.master_entries(out)
        self.assertEqual([uri for _, uri in entries], ["720p/stream.m3u8", "480p/stream.m3u8", "360p/stream.m3u8"])

        segment_lists = []
        for attrs, uri in entries:
            self.assertEqual(attrs["CODECS"].strip('"').split(",")[1], "mp4a.40.2")
            variant_dir = os.path.join(out, os.path.dirname(uri))
            segments = read_media_playlist(os.path.join(out, uri))
            durations = [d for d, _ in segments]
            segment_lists.append(durations)
            self.assertTrue(all(d <= 6.1 for d in durations), durations)
            # Declared peak must cover every full segment's real bitrate.
            for duration, seg in segments:
                if duration >= 3:
                    actual = os.path.getsize(os.path.join(variant_dir, seg)) * 8 / duration
                    self.assertGreaterEqual(int(attrs["BANDWIDTH"]), int(actual))
        # Same cut points in every rendition, so quality switches are seamless.
        self.assertEqual(segment_lists[0], segment_lists[1])
        self.assertEqual(segment_lists[0], segment_lists[2])

        self.assertEqual(s3.extra_args["landscape/720p/000.ts"]["ContentType"], "video/mp2t")
        self.assertEqual(s3.extra_args["landscape/sprite.vtt"]["ContentType"], "text/vtt")

        poster = probe_stream(os.path.join(out, "poster.jpg"), "v:0", "width,height")
        self.assertEqual((poster["width"], poster["height"]), (1280, 720))

    def test_rotated_phone_video_stays_portrait(self):
        out, _, _ = self.run_pipeline("phone")
        self.assert_common_outputs(out)
        top = probe_stream(os.path.join(out, "720p", "000.ts"), "v:0", "width,height")
        self.assertEqual((top["width"], top["height"]), (720, 1280))
        resolutions = [attrs["RESOLUTION"] for attrs, _ in self.master_entries(out)]
        self.assertIn("720x1280", resolutions)
        with open(os.path.join(out, "sprite.vtt")) as f:
            self.assertIn("#xywh=0,0,122,216", f.read())

    def test_tiny_source_without_audio(self):
        out, _, _ = self.run_pipeline("tiny")
        self.assert_common_outputs(out)
        entries = self.master_entries(out)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0][0]["RESOLUTION"], "320x240")
        self.assertNotIn("mp4a", entries[0][0]["CODECS"])
        self.assertEqual(probe_stream(os.path.join(out, "360p", "000.ts"), "a:0", "codec_name"), {})

    def test_one_second_clip_gets_valid_thumbnails(self):
        out, _, _ = self.run_pipeline("blip")
        self.assert_common_outputs(out)
        with open(os.path.join(out, "sprite.vtt")) as f:
            vtt = f.read()
        self.assertIn("00:00:00.000 --> 00:00:00.010", vtt)
        self.assertTrue(vtt.rstrip().splitlines()[-2].endswith("--> 00:00:01.000"))


if __name__ == "__main__":
    unittest.main()
