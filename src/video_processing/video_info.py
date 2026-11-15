import json
import subprocess
from dataclasses import dataclass

from src.logging_config import logger


MAX_PLAUSIBLE_FPS = 240


@dataclass(frozen=True)
class VideoInfo:
    """What the pipeline needs to know about a source file.

    width/height are the *display* size: rotation metadata (phones record
    portrait video as rotated landscape) and non-square pixels are already
    applied, so they match the frames ffmpeg hands to the filter graph.
    """

    width: int
    height: int
    duration: float
    fps: float
    has_audio: bool
    bitrate_kbps: int


def probe_video(path):
    """Read a source file with ffprobe. Raises ValueError if it is not a usable video."""
    logger.info(f"Probing {path}")
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise ValueError(f"ffprobe could not read {path}: {result.stderr.strip()[-500:]}")
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        raise ValueError(f"ffprobe returned invalid JSON for {path}: {e}") from e

    info = parse_probe(data)
    logger.info(f"Video info: {info}")
    return info


def parse_probe(data):
    streams = data.get("streams", [])
    fmt = data.get("format", {})

    video = next(
        (
            s
            for s in streams
            if s.get("codec_type") == "video"
            # Cover art in audio files shows up as a one-frame video stream.
            and not s.get("disposition", {}).get("attached_pic")
        ),
        None,
    )
    if video is None:
        raise ValueError("No video stream found")

    width = int(video.get("width") or 0)
    height = int(video.get("height") or 0)
    if width <= 0 or height <= 0:
        raise ValueError("Video stream has no dimensions")

    sar = _parse_ratio(video.get("sample_aspect_ratio"))
    if sar and abs(sar - 1) > 0.01:
        width = round(width * sar)
    if abs(_rotation(video)) % 180 == 90:
        width, height = height, width

    duration = _first_positive(fmt.get("duration"), video.get("duration"))
    if duration <= 0:
        raise ValueError("Could not determine video duration")

    # avg_frame_rate is right for variable-frame-rate phone video, where
    # r_frame_rate can be a timebase like 90000. But WebM/Matroska without a
    # frame count often reports avg_frame_rate as its 1 ms timebase (1000/1),
    # which would mark a 30 fps file as high frame rate.
    fps = next(
        (
            rate
            for rate in (_parse_ratio(video.get("avg_frame_rate")), _parse_ratio(video.get("r_frame_rate")))
            if rate and rate <= MAX_PLAUSIBLE_FPS
        ),
        30.0,
    )

    return VideoInfo(
        width=width,
        height=height,
        duration=duration,
        fps=fps,
        has_audio=any(s.get("codec_type") == "audio" for s in streams),
        bitrate_kbps=int(fmt.get("bit_rate") or 0) // 1000,
    )


def _rotation(stream):
    for side_data in stream.get("side_data_list", []):
        if "rotation" in side_data:
            return int(round(float(side_data["rotation"])))
    rotate_tag = stream.get("tags", {}).get("rotate")
    return int(rotate_tag) if rotate_tag else 0


def _parse_ratio(value):
    """Parse '30000/1001' or '16:9'. Returns None for missing or zero values like '0/0'."""
    if not value:
        return None
    sep = ":" if ":" in value else "/"
    try:
        num, den = (float(part) for part in value.split(sep))
    except ValueError:
        return None
    if num <= 0 or den <= 0:
        return None
    return num / den


def _first_positive(*values):
    for value in values:
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if number > 0:
            return number
    return 0.0
