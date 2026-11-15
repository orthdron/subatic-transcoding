import os
import tempfile
import unittest

from src.video_processing.hls_generator import (
    measure_bandwidth,
    order_for_startup,
    read_media_playlist,
)
from src.video_processing.ladder import build_ladder


class MediaPlaylistTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()

    def write_variant(self, segments):
        lines = ["#EXTM3U", "#EXT-X-VERSION:3", "#EXT-X-TARGETDURATION:6"]
        for i, (duration, size) in enumerate(segments):
            name = f"{i:03d}.ts"
            with open(os.path.join(self.dir, name), "wb") as f:
                f.write(b"\0" * size)
            lines += [f"#EXTINF:{duration:.6f},", name]
        lines.append("#EXT-X-ENDLIST")
        with open(os.path.join(self.dir, "stream.m3u8"), "w") as f:
            f.write("\n".join(lines))
        return read_media_playlist(os.path.join(self.dir, "stream.m3u8"))

    def test_reads_durations_and_uris(self):
        segments = self.write_variant([(6.0, 10), (6.0, 10), (1.5, 10)])
        self.assertEqual(segments, [(6.0, "000.ts"), (6.0, "001.ts"), (1.5, "002.ts")])

    def test_peak_and_average(self):
        # 750 KB per 6 s = 1 Mbit/s; one 1.5 MB segment = 2 Mbit/s
        segments = self.write_variant([(6.0, 750_000), (6.0, 1_500_000), (6.0, 750_000)])
        peak, average = measure_bandwidth(self.dir, segments)
        self.assertEqual(peak, 2_000_000)
        self.assertEqual(average, int(3_000_000 * 8 / 18))

    def test_short_last_segment_does_not_inflate_peak(self):
        # The 0.5 s tail alone would read as 4 Mbit/s; merged with the segment
        # before it, the window is ~1.23 Mbit/s.
        segments = self.write_variant([(6.0, 750_000), (6.0, 750_000), (0.5, 250_000)])
        peak, _ = measure_bandwidth(self.dir, segments)
        self.assertLess(peak, 1_300_000)


class StartupOrderTest(unittest.TestCase):
    def entries(self, width, height):
        return [(r, (i + 1) * 1_000_000, 0, None) for i, r in enumerate(build_ladder(width, height))]

    def test_720p_listed_first_then_descending(self):
        ordered = [e[0].name for e in order_for_startup(self.entries(3840, 2160))]
        self.assertEqual(ordered, ["720p", "2160p", "1440p", "1080p", "480p", "360p"])

    def test_small_source_starts_on_its_best_rendition(self):
        ordered = [e[0].name for e in order_for_startup(self.entries(854, 480))]
        self.assertEqual(ordered, ["480p", "360p"])


if __name__ == "__main__":
    unittest.main()
