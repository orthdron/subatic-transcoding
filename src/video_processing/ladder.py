from dataclasses import dataclass


@dataclass(frozen=True)
class Rung:
    """One step of the quality ladder: a 16:9 box plus bitrate ceilings."""

    long_side: int
    short_side: int
    video_kbps: int  # peak video bitrate allowed at <= 30 fps
    audio_kbps: int


# Smallest first. Ceilings are for H.264 at CRF 23: CRF decides quality, the
# ceiling only stops hard-to-encode scenes from spiking past what the
# rendition's bandwidth class can stream.
LADDER = (
    Rung(640, 360, 900, 96),
    Rung(854, 480, 1500, 96),
    Rung(1280, 720, 3000, 128),
    Rung(1920, 1080, 5500, 128),
    Rung(2560, 1440, 9000, 160),
    Rung(3840, 2160, 16000, 160),
)

HIGH_FPS_THRESHOLD = 40
HIGH_FPS_BITRATE_MULTIPLIER = 1.5


@dataclass(frozen=True)
class Rendition:
    name: str  # rung label, also the output folder, e.g. "720p"
    rung_short_side: int
    width: int
    height: int
    video_kbps: int
    audio_kbps: int

    @property
    def resolution(self):
        return f"{self.width}x{self.height}"


def oriented_box(long_side, short_side, width, height):
    """Turn a landscape box to portrait when the source is portrait."""
    return (short_side, long_side) if height > width else (long_side, short_side)


def fit_within(width, height, box_width, box_height):
    """Scale width x height down to fit the box, keeping aspect ratio.

    Never upscales. Both sides come out even, as yuv420p requires.
    """
    scale = min(1.0, box_width / width, box_height / height)
    return _even(width * scale), _even(height * scale)


# A rung less than this much bigger (in pixels) than the previous one is
# merged into it instead of becoming a near-identical extra rendition.
NEAR_DUPLICATE_RATIO = 1.15


def build_ladder(width, height, fps=30.0):
    """Renditions for a source of this display size, smallest first.

    Each rung's box is turned to match the source orientation, and the source
    is fitted inside it without upscaling. A rung that comes out the same size
    as (or barely bigger than) the previous one is merged into it, keeping the
    larger size. So:
      - portrait 1080x1920 gets 360x640 ... 1080x1920 (rungs by short side)
      - 1600x900 (between rungs) keeps a native-size top rendition
      - 1366x768 becomes a native-size "720p" rather than 1280x720 + 1366x768
      - anything smaller than 640x360 still gets one rendition at native size
    """
    renditions = []
    rungs = []
    for rung in LADDER:
        box_w, box_h = oriented_box(rung.long_side, rung.short_side, width, height)
        w, h = fit_within(width, height, box_w, box_h)

        if renditions:
            prev = renditions[-1]
            prev_pixels = prev.width * prev.height
            if w * h <= prev_pixels * NEAR_DUPLICATE_RATIO:
                if w * h > prev_pixels:
                    renditions[-1] = _make_rendition(rungs[-1], w, h, width, height, fps)
                continue

        rungs.append(rung)
        renditions.append(_make_rendition(rung, w, h, width, height, fps))
    return renditions


def _make_rendition(rung, w, h, source_width, source_height, fps):
    box_w, box_h = oriented_box(rung.long_side, rung.short_side, source_width, source_height)
    # Ceilings assume a full 16:9 frame; scale them with the actual pixel
    # count (4:3, ultrawide, tiny sources) so the cap stays meaningful.
    pixel_ratio = max(0.5, (w * h) / (box_w * box_h))
    video_kbps = rung.video_kbps * pixel_ratio
    if fps > HIGH_FPS_THRESHOLD:
        video_kbps *= HIGH_FPS_BITRATE_MULTIPLIER
    return Rendition(
        name=f"{rung.short_side}p",
        rung_short_side=rung.short_side,
        width=w,
        height=h,
        video_kbps=int(round(video_kbps)),
        audio_kbps=rung.audio_kbps,
    )


def _even(value):
    rounded = int(round(value))
    return max(2, rounded - rounded % 2)
