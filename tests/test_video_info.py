import unittest

from src.video_processing.video_info import parse_probe


def probe(video=None, audio=True, fmt=None):
    streams = []
    if video is not False:
        streams.append({"codec_type": "video", "width": 1920, "height": 1080, "avg_frame_rate": "30/1", **(video or {})})
    if audio:
        streams.append({"codec_type": "audio"})
    return {"streams": streams, "format": {"duration": "12.5", "bit_rate": "4000000", **(fmt or {})}}


class ParseProbeTest(unittest.TestCase):
    def test_basic_fields(self):
        info = parse_probe(probe())
        self.assertEqual((info.width, info.height), (1920, 1080))
        self.assertEqual(info.duration, 12.5)
        self.assertEqual(info.fps, 30.0)
        self.assertTrue(info.has_audio)
        self.assertEqual(info.bitrate_kbps, 4000)

    def test_phone_rotation_swaps_dimensions(self):
        info = parse_probe(probe({"side_data_list": [{"side_data_type": "Display Matrix", "rotation": -90}]}))
        self.assertEqual((info.width, info.height), (1080, 1920))

    def test_legacy_rotate_tag(self):
        info = parse_probe(probe({"tags": {"rotate": "270"}}))
        self.assertEqual((info.width, info.height), (1080, 1920))

    def test_upside_down_does_not_swap(self):
        info = parse_probe(probe({"side_data_list": [{"rotation": 180}]}))
        self.assertEqual((info.width, info.height), (1920, 1080))

    def test_anamorphic_pixels_use_display_width(self):
        info = parse_probe(probe({"width": 720, "height": 480, "sample_aspect_ratio": "32:27"}))
        self.assertEqual((info.width, info.height), (853, 480))

    def test_falls_back_to_stream_duration(self):
        info = parse_probe(probe({"duration": "7.0"}, fmt={"duration": None}))
        self.assertEqual(info.duration, 7.0)

    def test_missing_duration_is_an_error(self):
        with self.assertRaises(ValueError):
            parse_probe(probe(fmt={"duration": "N/A"}))

    def test_no_audio(self):
        self.assertFalse(parse_probe(probe(audio=False)).has_audio)

    def test_cover_art_is_not_a_video(self):
        data = probe(video={"disposition": {"attached_pic": 1}})
        with self.assertRaises(ValueError):
            parse_probe(data)

    def test_frame_rate_fallback(self):
        info = parse_probe(probe({"avg_frame_rate": "0/0", "r_frame_rate": "60000/1001"}))
        self.assertAlmostEqual(info.fps, 59.94, places=2)


if __name__ == "__main__":
    unittest.main()
