import unittest

from src.video_processing.ladder import build_ladder, fit_within


def sizes(renditions):
    return [(r.name, r.resolution) for r in renditions]


class BuildLadderTest(unittest.TestCase):
    def test_4k_landscape_gets_full_ladder(self):
        self.assertEqual(
            sizes(build_ladder(3840, 2160)),
            [
                ("360p", "640x360"),
                ("480p", "852x480"),
                ("720p", "1280x720"),
                ("1080p", "1920x1080"),
                ("1440p", "2560x1440"),
                ("2160p", "3840x2160"),
            ],
        )

    def test_1080p_stops_at_source_size(self):
        self.assertEqual(sizes(build_ladder(1920, 1080))[-1], ("1080p", "1920x1080"))
        self.assertEqual(len(build_ladder(1920, 1080)), 4)

    def test_sources_below_480p_still_get_a_rendition(self):
        self.assertEqual(sizes(build_ladder(640, 360)), [("360p", "640x360")])
        self.assertEqual(sizes(build_ladder(320, 240)), [("360p", "320x240")])

    def test_portrait_uses_short_side_and_keeps_full_resolution(self):
        self.assertEqual(
            sizes(build_ladder(1080, 1920)),
            [
                ("360p", "360x640"),
                ("480p", "480x852"),
                ("720p", "720x1280"),
                ("1080p", "1080x1920"),
            ],
        )

    def test_source_between_rungs_keeps_native_top_rendition(self):
        self.assertEqual(sizes(build_ladder(1600, 900))[-1], ("1080p", "1600x900"))

    def test_near_duplicate_sizes_merge_into_the_larger(self):
        self.assertEqual(sizes(build_ladder(1366, 768))[-1], ("720p", "1366x768"))
        self.assertEqual(len(build_ladder(1366, 768)), 3)
        self.assertEqual(sizes(build_ladder(1920, 1088))[-1], ("1080p", "1920x1088"))

    def test_ultrawide_is_bounded_by_width(self):
        self.assertEqual(sizes(build_ladder(3840, 1600))[3], ("1080p", "1920x800"))

    def test_all_dimensions_even_and_never_upscaled(self):
        for w, h in [(1281, 721), (1279, 719), (853, 481), (3000, 2000), (101, 77)]:
            for r in build_ladder(w, h):
                self.assertEqual(r.width % 2, 0, (w, h, r))
                self.assertEqual(r.height % 2, 0, (w, h, r))
                self.assertLessEqual(r.width, w + 1)
                self.assertLessEqual(r.height, h + 1)

    def test_bitrate_and_audio_rise_with_quality(self):
        ladder = build_ladder(3840, 2160)
        video = [r.video_kbps for r in ladder]
        audio = [r.audio_kbps for r in ladder]
        self.assertEqual(video, sorted(video))
        self.assertEqual(audio, sorted(audio))

    def test_high_frame_rate_raises_ceiling(self):
        normal = build_ladder(1920, 1080, fps=30)[-1].video_kbps
        high = build_ladder(1920, 1080, fps=60)[-1].video_kbps
        self.assertGreater(high, normal)


class FitWithinTest(unittest.TestCase):
    def test_never_upscales(self):
        self.assertEqual(fit_within(320, 240, 1920, 1080), (320, 240))

    def test_keeps_aspect_ratio(self):
        self.assertEqual(fit_within(1920, 1080, 384, 216), (384, 216))
        self.assertEqual(fit_within(1080, 1920, 384, 216), (122, 216))


if __name__ == "__main__":
    unittest.main()
