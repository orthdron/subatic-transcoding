import json
import subprocess

from src.logging_config import logger


def run_ffmpeg(args, description):
    """Run ffmpeg non-interactively. Raises RuntimeError with ffmpeg's own error text."""
    cmd = ["ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "error", "-y", *args]
    logger.info(f"Running ffmpeg ({description})")
    logger.debug(" ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True)
    stderr = result.stderr.strip()
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed ({description}): {stderr[-2000:]}")
    if stderr:
        # At -loglevel error, output on success means recoverable problems such
        # as corrupt frames in the source. Worth seeing, not worth failing on.
        logger.warning(f"ffmpeg reported problems ({description}): {stderr[-1000:]}")


def probe_stream(path, select, entries):
    """Return the first matching stream's fields from ffprobe, or {} if none."""
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        select,
        "-show_entries",
        f"stream={entries}",
        "-of",
        "json",
        path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return {}
    streams = json.loads(result.stdout or "{}").get("streams", [])
    return streams[0] if streams else {}
