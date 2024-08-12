import json
import subprocess
from moviepy.editor import VideoFileClip
from src.logging_config import logger


def is_video_file_fine(input_file):
    try:
        with VideoFileClip(input_file) as video_clip:
            return True
    except Exception as e:
        logger.error(f"Error checking video file: {e}")
        return False


def get_video_info(filename):
    logger.info(f"Getting video info for file: {filename}")
    try:
        cmd = [
            "ffprobe",
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            filename,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            raise subprocess.CalledProcessError(result.returncode, cmd, result.stderr)

        probe_data = json.loads(result.stdout)

        video_stream = next(
            (
                stream
                for stream in probe_data["streams"]
                if stream["codec_type"] == "video"
            ),
            None,
        )

        if not video_stream:
            raise ValueError("No video stream found")

        duration = float(probe_data["format"].get("duration", 0))
        bitrate = int(probe_data["format"].get("bit_rate", 0)) // 1000

        info = {
            "duration": duration,
            "width": int(video_stream["width"]),
            "height": int(video_stream["height"]),
            "bitrate": bitrate,
        }

        logger.info(f"Extracted video info: {info}")
        return info

    except subprocess.CalledProcessError as e:
        logger.error(f"FFprobe command failed: {e.stderr}", exc_info=True)
        raise
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse FFprobe output: {str(e)}", exc_info=True)
        raise
    except Exception as e:
        logger.error(
            f"Error getting video info for '{filename}': {str(e)}", exc_info=True
        )
        raise
