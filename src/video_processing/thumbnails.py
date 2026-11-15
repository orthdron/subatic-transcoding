import glob
import math
import os

from PIL import Image

from src.logging_config import logger
from src.video_processing.ffmpeg_cli import run_ffmpeg
from src.video_processing.hls_generator import THUMBNAIL_COUNT, THUMBNAIL_FRAME_PATTERN
from src.video_processing.ladder import fit_within, oriented_box

SPRITE_COLUMNS = 10
POSTER_BOX = (1920, 1080)

# Card previews for the web app's video grid, at the thumbnail frame size
# (grid tiles are 16:9 and about 300-480 CSS px wide).
#
# short.webp loops at rest on every card: 10 frames, 5 s each. Animated WebP
# still works in a plain <img> and is about 7x smaller than a GIF.
SHORT_PREVIEW_FRAMES = 10
SHORT_PREVIEW_FRAME_MS = 5000
SHORT_PREVIEW_QUALITY = 70
# Pillow's default (0) is ~35% bigger; 4 takes ~50 ms here, 6 is 40x slower for ~3% less.
SHORT_PREVIEW_METHOD = 4
# long.mp4 plays on hover: every thumbnail frame, 0.5 s each. Neighbouring
# frames look alike, so H.264 is 2-3x smaller than animated WebP and 15x
# smaller than GIF. The clip is always THUMBNAIL_COUNT / LONG_PREVIEW_FPS
# = 50 s, so the bitrate cap bounds the file at about 250 KB for any content.
LONG_PREVIEW_FPS = 2
LONG_PREVIEW_CRF = 28
LONG_PREVIEW_MAX_KBPS = 40


def create_thumbnails(input_file, frames_dir, output_dir, info):
    """Build sprite.jpg + sprite.vtt, short.webp, long.mp4 and poster.jpg.

    The small frames come from the HLS run (frames_dir); the poster is grabbed
    separately at full quality from the middle of the video.
    """
    images = load_frames(frames_dir)
    tile_w, tile_h = images[0].size

    create_sprite(images, output_dir)
    with open(os.path.join(output_dir, "sprite.vtt"), "w") as f:
        f.write(build_sprite_vtt(len(images), tile_w, tile_h, info.duration))

    create_previews(images, frames_dir, output_dir)

    poster_path = os.path.join(output_dir, "poster.jpg")
    poster_w, poster_h = fit_within(
        info.width, info.height, *oriented_box(*POSTER_BOX, info.width, info.height)
    )
    extract_poster(input_file, poster_path, info.duration / 2, poster_w, poster_h)
    if not os.path.exists(poster_path):
        logger.warning("Full-size poster extraction produced nothing; using a thumbnail frame")
        images[len(images) // 2].save(poster_path, quality=90)

    logger.info(f"Thumbnails created from {len(images)} frames ({tile_w}x{tile_h} tiles)")


def load_frames(frames_dir):
    paths = sorted(glob.glob(os.path.join(frames_dir, "frame*.jpg")))[:THUMBNAIL_COUNT]
    if not paths:
        raise RuntimeError("No thumbnail frames were extracted")
    images = []
    for path in paths:
        with Image.open(path) as image:
            images.append(image.convert("RGB"))
    return images


def create_sprite(images, output_dir):
    tile_w, tile_h = images[0].size
    rows = math.ceil(len(images) / SPRITE_COLUMNS)
    sprite = Image.new("RGB", (SPRITE_COLUMNS * tile_w, rows * tile_h))
    for i, image in enumerate(images):
        sprite.paste(image, ((i % SPRITE_COLUMNS) * tile_w, (i // SPRITE_COLUMNS) * tile_h))
    sprite.save(os.path.join(output_dir, "sprite.jpg"), quality=85)


def build_sprite_vtt(count, tile_w, tile_h, duration, image_name="sprite.jpg"):
    """WebVTT thumbnail track: one cue per tile, back to back from 0 to duration."""
    total_ms = int(round(duration * 1000))
    lines = ["WEBVTT", ""]
    for i in range(count):
        start_ms = total_ms * i // count
        end_ms = total_ms * (i + 1) // count
        x = (i % SPRITE_COLUMNS) * tile_w
        y = (i // SPRITE_COLUMNS) * tile_h
        lines.append(f"{format_vtt_timestamp(start_ms)} --> {format_vtt_timestamp(end_ms)}")
        lines.append(f"{image_name}#xywh={x},{y},{tile_w},{tile_h}")
        lines.append("")
    return "\n".join(lines)


def format_vtt_timestamp(milliseconds):
    hours, rest = divmod(milliseconds, 3_600_000)
    minutes, rest = divmod(rest, 60_000)
    seconds, millis = divmod(rest, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{millis:03d}"


def create_previews(images, frames_dir, output_dir):
    """short.webp (loops at rest) and long.mp4 (plays on hover) for the video grid cards."""
    step = max(1, len(images) // SHORT_PREVIEW_FRAMES)
    short_frames = images[::step][:SHORT_PREVIEW_FRAMES]
    short_frames[0].save(
        os.path.join(output_dir, "short.webp"),
        append_images=short_frames[1:],
        save_all=True,
        duration=SHORT_PREVIEW_FRAME_MS,
        loop=0,
        quality=SHORT_PREVIEW_QUALITY,
        method=SHORT_PREVIEW_METHOD,
    )
    run_ffmpeg(
        [
            "-framerate", str(LONG_PREVIEW_FPS),
            "-start_number", "1",
            "-i", os.path.join(frames_dir, THUMBNAIL_FRAME_PATTERN),
            "-frames:v", str(len(images)),
            # The JPEG frames are full range; browsers expect TV-range H.264.
            "-vf", "scale=out_range=tv",
            "-c:v", "libx264",
            "-preset", "slow",
            "-crf", str(LONG_PREVIEW_CRF),
            "-maxrate", f"{LONG_PREVIEW_MAX_KBPS}k",
            "-bufsize", f"{LONG_PREVIEW_MAX_KBPS * 2}k",
            "-pix_fmt", "yuv420p",
            "-an",
            # moov first, so the browser can start playing before the download ends.
            "-movflags", "+faststart",
            os.path.join(output_dir, "long.mp4"),
        ],
        "long preview",
    )


def extract_poster(input_file, output_path, at_seconds, width, height):
    run_ffmpeg(
        [
            "-ss", f"{at_seconds:.3f}",
            "-i", input_file,
            "-frames:v", "1",
            "-vf", f"scale={width}:{height},setsar=1",
            "-q:v", "2",
            output_path,
        ],
        "poster",
    )
