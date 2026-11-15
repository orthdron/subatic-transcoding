import os
import tempfile
import unittest
from unittest import mock

from src.s3_operations.upload import plan_upload, upload_args, upload_directory
from src.video_processing.workspace import Workspace


def touch(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "w").close()


class UploadTest(unittest.TestCase):
    def setUp(self):
        root = tempfile.mkdtemp()
        self.workspace = Workspace(
            root=root,
            source=os.path.join(root, "source", "vid1"),
            output=os.path.join(root, "output"),
            frames=os.path.join(root, "frames"),
        )
        touch(self.workspace.source)
        for name in ["master.m3u8", "poster.jpg", "sprite.vtt", "720p/stream.m3u8", "720p/000.ts"]:
            touch(os.path.join(self.workspace.output, name))

    def test_raw_source_is_never_uploaded(self):
        keys = [key for batch in plan_upload(self.workspace.output, "vid1") for _, key in batch]
        self.assertNotIn("vid1/vid1", keys)
        self.assertFalse(any("source" in key for key in keys))

    def test_master_playlist_goes_last(self):
        batches = plan_upload(self.workspace.output, "vid1")
        self.assertEqual([key for _, key in batches[-1]], ["vid1/master.m3u8"])
        self.assertEqual([key for _, key in batches[-2]], ["vid1/720p/stream.m3u8"])
        self.assertEqual(
            sorted(key for _, key in batches[0]),
            ["vid1/720p/000.ts", "vid1/poster.jpg", "vid1/sprite.vtt"],
        )

    def test_content_types_and_caching(self):
        self.assertEqual(upload_args("a/stream.m3u8")["ContentType"], "application/vnd.apple.mpegurl")
        self.assertEqual(upload_args("a/000.ts")["ContentType"], "video/mp2t")
        self.assertEqual(upload_args("sprite.vtt")["ContentType"], "text/vtt")
        self.assertEqual(upload_args("poster.jpg")["ContentType"], "image/jpeg")
        self.assertEqual(upload_args("short.webp")["ContentType"], "image/webp")
        self.assertEqual(upload_args("long.mp4")["ContentType"], "video/mp4")
        self.assertIn("immutable", upload_args("a/000.ts")["CacheControl"])
        self.assertNotIn("immutable", upload_args("master.m3u8")["CacheControl"])

    def test_upload_passes_headers_to_s3(self):
        client = mock.Mock()
        upload_directory(self.workspace.output, "vid1", s3_client=client)
        calls = {c.args[2]: c.kwargs["ExtraArgs"] for c in client.upload_file.call_args_list}
        self.assertEqual(len(calls), 5)
        self.assertEqual(calls["vid1/720p/000.ts"]["ContentType"], "video/mp2t")
        self.assertEqual(client.upload_file.call_args_list[-1].args[2], "vid1/master.m3u8")

    def test_upload_failure_raises(self):
        client = mock.Mock()
        client.upload_file.side_effect = RuntimeError("boom")
        with self.assertRaises(RuntimeError):
            upload_directory(self.workspace.output, "vid1", s3_client=client)


if __name__ == "__main__":
    unittest.main()
