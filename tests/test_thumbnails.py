import re
import unittest

from src.video_processing.thumbnails import build_sprite_vtt, format_vtt_timestamp

CUE = re.compile(r"^(\d{2}):(\d{2}):(\d{2})\.(\d{3}) --> (\d{2}):(\d{2}):(\d{2})\.(\d{3})$")


def cue_times(vtt):
    times = []
    for line in vtt.splitlines():
        match = CUE.match(line)
        if match:
            g = [int(x) for x in match.groups()]
            start = ((g[0] * 60 + g[1]) * 60 + g[2]) * 1000 + g[3]
            end = ((g[4] * 60 + g[5]) * 60 + g[6]) * 1000 + g[7]
            times.append((start, end))
    return times


class SpriteVttTest(unittest.TestCase):
    def test_timestamps_have_milliseconds(self):
        self.assertEqual(format_vtt_timestamp(3_723_456), "01:02:03.456")
        self.assertEqual(format_vtt_timestamp(0), "00:00:00.000")

    def test_short_video_cues_are_contiguous_and_non_empty(self):
        times = cue_times(build_sprite_vtt(100, 384, 216, duration=30.0))
        self.assertEqual(len(times), 100)
        self.assertEqual(times[0][0], 0)
        self.assertEqual(times[-1][1], 30_000)
        for (start, end), (next_start, _) in zip(times, times[1:]):
            self.assertLess(start, end)
            self.assertEqual(end, next_start)

    def test_tile_positions_follow_grid(self):
        vtt = build_sprite_vtt(12, 120, 216, duration=12.0)
        self.assertIn("sprite.jpg#xywh=0,0,120,216", vtt)
        self.assertIn("sprite.jpg#xywh=1080,0,120,216", vtt)  # 10th tile
        self.assertIn("sprite.jpg#xywh=0,216,120,216", vtt)  # 11th tile wraps
        self.assertTrue(vtt.startswith("WEBVTT\n\n"))


if __name__ == "__main__":
    unittest.main()
