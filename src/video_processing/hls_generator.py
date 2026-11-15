import os
import re

from src.logging_config import logger
from src.video_processing.ffmpeg_cli import probe_stream, run_ffmpeg
from src.video_processing.ladder import build_ladder, fit_within

SEGMENT_SECONDS = 6
# Keyframes on a fixed 2 s grid (a divisor of SEGMENT_SECONDS) make every
# rendition cut its segments at the same timestamps, so players can switch
# quality at any segment boundary without a glitch.
KEYFRAME_SECONDS = 2
CRF = 23
PRESET = "veryfast"

THUMBNAIL_COUNT = 100
THUMBNAIL_BOX = (384, 216)
THUMBNAIL_FRAME_PATTERN = "frame%03d.jpg"  # ffmpeg numbers them from 001

# The rendition players start on (listed first in the master playlist).
# Starting at the top rendition makes the first seconds slow on most links.
START_RUNG_SHORT_SIDE = 720

AUDIO_CODEC = "mp4a.40.2"  # AAC-LC, ffmpeg's default aac profile
H264_PROFILE_IDC = {
    "High": "6400",
    "Main": "4d40",
    "Constrained Baseline": "42e0",
    "Baseline": "4200",
}


def create_adaptive_hls(input_file, output_dir, frames_dir, info, rendition_root=""):
    """Encode every rendition plus the thumbnail frames in one ffmpeg run.

    The source is decoded once and split, instead of once per rendition.
    Writes <output_dir>/[<rendition_root>/]<rendition>/stream.m3u8 + segments,
    thumbnail JPEGs to frames_dir, and <output_dir>/master.m3u8 with measured
    bandwidths. A rendition_root gives a re-transcode segment URLs that were
    never served before (see backfill.py). Returns the renditions, smallest first.
    """
    renditions = build_ladder(info.width, info.height, info.fps)
    logger.info(
        "Renditions: " + ", ".join(f"{r.name} {r.resolution} <= {r.video_kbps}k" for r in renditions)
    )
    thumb_w, thumb_h = fit_within(info.width, info.height, *THUMBNAIL_BOX)

    for rendition in renditions:
        os.makedirs(os.path.join(output_dir, rendition_path(rendition, rendition_root)), exist_ok=True)
    os.makedirs(frames_dir, exist_ok=True)

    args = build_ffmpeg_args(
        input_file, output_dir, frames_dir, info, renditions, (thumb_w, thumb_h), rendition_root
    )
    run_ffmpeg(args, f"HLS x{len(renditions)} + thumbnails")

    write_master_playlist(output_dir, renditions, info.has_audio, rendition_root)
    return renditions


def rendition_path(rendition, rendition_root=""):
    """Folder of a rendition relative to the output dir, with '/' separators (it is also a URL path)."""
    return f"{rendition_root}/{rendition.name}" if rendition_root else rendition.name


def build_ffmpeg_args(input_file, output_dir, frames_dir, info, renditions, thumb_size, rendition_root=""):
    branches = len(renditions) + 1  # +1 for thumbnail frames
    labels = [f"[v{i}]" for i in range(branches)]
    filters = [f"[0:v:0]split={branches}{''.join(labels)}"]
    for i, r in enumerate(renditions):
        filters.append(f"[v{i}]scale={r.width}:{r.height},setsar=1,format=yuv420p[out{i}]")
    thumb_fps = THUMBNAIL_COUNT / info.duration
    filters.append(
        f"[v{len(renditions)}]fps={thumb_fps:.6f},"
        f"scale={thumb_size[0]}:{thumb_size[1]},setsar=1[thumbs]"
    )

    args = ["-i", input_file, "-filter_complex", ";".join(filters)]

    for i, r in enumerate(renditions):
        variant_dir = os.path.join(output_dir, rendition_path(r, rendition_root))
        args += ["-map", f"[out{i}]"]
        if info.has_audio:
            args += ["-map", "0:a:0"]
        args += [
            "-c:v", "libx264",
            "-preset", PRESET,
            "-profile:v", "high",
            "-crf", str(CRF),
            "-maxrate", f"{r.video_kbps}k",
            "-bufsize", f"{r.video_kbps * 2}k",
            "-force_key_frames", f"expr:gte(t,n_forced*{KEYFRAME_SECONDS})",
        ]
        if info.has_audio:
            args += ["-c:a", "aac", "-b:a", f"{r.audio_kbps}k", "-ac", "2", "-ar", "48000"]
        args += [
            "-f", "hls",
            "-hls_time", str(SEGMENT_SECONDS),
            "-hls_playlist_type", "vod",
            "-hls_flags", "independent_segments",
            "-hls_segment_filename", os.path.join(variant_dir, "%03d.ts"),
            os.path.join(variant_dir, "stream.m3u8"),
        ]

    args += ["-map", "[thumbs]", "-q:v", "3", os.path.join(frames_dir, THUMBNAIL_FRAME_PATTERN)]
    return args


def write_master_playlist(output_dir, renditions, has_audio, rendition_root=""):
    entries = []
    version = 3
    for r in renditions:
        variant_dir = os.path.join(output_dir, rendition_path(r, rendition_root))
        playlist_path = os.path.join(variant_dir, "stream.m3u8")
        segments = read_media_playlist(playlist_path)
        if not segments:
            raise RuntimeError(f"Rendition {r.name} produced no segments")
        peak, average = measure_bandwidth(variant_dir, segments)
        codecs = variant_codecs(os.path.join(variant_dir, segments[0][1]), has_audio)
        entries.append((r, peak, average, codecs))
        version = max(version, playlist_version(playlist_path))

    # Declare the same protocol version as ffmpeg's media playlists.
    lines = ["#EXTM3U", f"#EXT-X-VERSION:{version}", "#EXT-X-INDEPENDENT-SEGMENTS"]
    for r, peak, average, codecs in order_for_startup(entries):
        attrs = f"BANDWIDTH={peak},AVERAGE-BANDWIDTH={average},RESOLUTION={r.resolution}"
        if codecs:
            attrs += f',CODECS="{codecs}"'
        lines.append(f"#EXT-X-STREAM-INF:{attrs}")
        lines.append(f"{rendition_path(r, rendition_root)}/stream.m3u8")

    with open(os.path.join(output_dir, "master.m3u8"), "w") as f:
        f.write("\n".join(lines) + "\n")

    for r, peak, average, _ in entries:
        logger.info(f"{r.name}: peak {peak // 1000}k, average {average // 1000}k")


def order_for_startup(entries):
    """Start rendition first, then the rest from highest to lowest bandwidth."""
    by_bandwidth = sorted(entries, key=lambda e: e[1], reverse=True)
    eligible = [e for e in entries if e[0].rung_short_side <= START_RUNG_SHORT_SIDE]
    start = max(eligible, key=lambda e: e[0].rung_short_side) if eligible else entries[0]
    return [start] + [e for e in by_bandwidth if e is not start]


def read_media_playlist(path):
    """Return [(duration_seconds, segment_uri), ...] from a media playlist."""
    segments = []
    duration = None
    with open(path) as f:
        for line in f:
            line = line.strip()
            match = re.match(r"#EXTINF:([\d.]+)", line)
            if match:
                duration = float(match.group(1))
            elif line and not line.startswith("#") and duration is not None:
                segments.append((duration, line))
                duration = None
    return segments


def playlist_version(path):
    with open(path) as f:
        match = re.search(r"^#EXT-X-VERSION:(\d+)", f.read(), re.MULTILINE)
    return int(match.group(1)) if match else 1


def measure_bandwidth(variant_dir, segments):
    """Peak and average bits/s, per the HLS spec's definitions.

    Peak is the highest rate over a run of segments lasting at least half the
    target duration, so a short final segment cannot inflate it on its own.
    """
    sizes = [os.path.getsize(os.path.join(variant_dir, uri)) * 8 for _, uri in segments]
    durations = [d for d, _ in segments]

    total_duration = sum(durations)
    average = int(sum(sizes) / total_duration) if total_duration else 0

    peak = 0
    min_window = SEGMENT_SECONDS / 2
    for i in range(len(segments)):
        bits, seconds, j = sizes[i], durations[i], i
        while seconds < min_window and j > 0:
            j -= 1
            bits += sizes[j]
            seconds += durations[j]
        if seconds > 0:
            peak = max(peak, int(bits / seconds))
    return peak, average


def variant_codecs(segment_path, has_audio):
    """RFC 6381 codec string such as 'avc1.640028,mp4a.40.2', or None if unknown."""
    stream = probe_stream(segment_path, "v:0", "profile,level")
    profile_idc = H264_PROFILE_IDC.get(stream.get("profile"))
    level = stream.get("level")
    if not profile_idc or not isinstance(level, int) or level <= 0:
        return None
    codecs = f"avc1.{profile_idc}{level:02x}"
    if has_audio:
        codecs += f",{AUDIO_CODEC}"
    return codecs
