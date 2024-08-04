import os
import time
import shutil
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv
import json
from decimal import Decimal
import logging
import requests

import boto3
import ffmpeg
from moviepy.editor import VideoFileClip
from PIL import Image
import glob

# Set up logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def send_webhook(video_id, status):
    webhook_url = os.getenv("WEBHOOK_URL")
    webhook_token = os.getenv("WEBHOOK_TOKEN")

    if not webhook_url or not webhook_token:
        logger.error("WEBHOOK_URL or WEBHOOK_TOKEN environment variable is missing")
        return

    if webhook_url.endswith("/"):
        webhook_url = webhook_url[:-1]

    webhook_url = f"{webhook_url}/api/video/updateStatus"

    payload = {"id": video_id, "status": status, "token": webhook_token}

    try:
        response = requests.post(webhook_url, json=payload)
        response.raise_for_status()
        logger.info(
            f"Webhook sent successfully for video {video_id} with status {status}"
        )
    except requests.RequestException as e:
        logger.error(f"Failed to send webhook for video {video_id}: {str(e)}")


def main():
    load_dotenv()
    sqs_session = boto3.Session(
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID_1"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY_1"),
        region_name=os.getenv("AWS_REGION"),
    )

    sqs_client = sqs_session.client("sqs")
    queue_url = os.getenv("AWS_SQS_URL")

    while True:
        try:
            process_message(sqs_client, queue_url)
        except Exception as e:
            logger.error(f"Error in main loop: {str(e)}")
        logger.info("Sleeping for 5 seconds...")
        time.sleep(5)


def process_message(sqs_client, queue_url):
    try:
        response = sqs_client.receive_message(
            QueueUrl=queue_url, MaxNumberOfMessages=1, WaitTimeSeconds=20
        )
        messages = response.get("Messages", [])
        if not messages:
            logger.info("No messages in the queue. Waiting...")
            return

        message = messages[0]
        message_data = message.get("Body")
        if not message_data:
            logger.warning("Received empty message body")
            return

        logger.info(f"Received message: {message_data}")
        parsed_message = json.loads(message_data)
        records = parsed_message.get("Records", [])
        for record in records:
            event_name = record.get("eventName")
            if event_name == "ObjectCreated:Put":
                object_key = record["s3"]["object"]["key"]
                if object_key:
                    try:
                        handler(object_key)
                    except Exception as e:
                        logger.error(f"Error processing message: {str(e)}")
                        send_webhook(object_key, "FAILED")
                else:
                    logger.warning(f"Invalid object key in message: {message_data}")

        # Delete the processed message from the queue
        sqs_client.delete_message(
            QueueUrl=queue_url, ReceiptHandle=message["ReceiptHandle"]
        )
    except Exception as e:
        logger.error(f"Error processing message: {str(e)}")


def setup(file_name):
    cleanup()
    folder_path = f"./upload/{file_name}"
    Path(folder_path).mkdir(parents=True, exist_ok=True)
    logger.info(f"Folder '{folder_path}' created successfully.")


def cleanup():
    folder_path = "./upload/"
    try:
        remove_files_with_wildcard("./input*")
        shutil.rmtree(folder_path)
        logger.info(f"Folder '{folder_path}' and its contents removed successfully.")
    except FileNotFoundError:
        logger.warning(f"Folder '{folder_path}' not found.")
    except OSError as e:
        logger.error(f"Error occurred while removing folder and its contents: {e}")


def remove_files_with_wildcard(file_pattern):
    files_to_remove = glob.glob(file_pattern)
    for file_path in files_to_remove:
        try:
            os.remove(file_path)
            logger.info(f"File '{file_path}' has been removed.")
        except FileNotFoundError:
            logger.warning(f"File '{file_path}' does not exist.")
        except OSError as e:
            logger.error(f"Error removing file '{file_path}': {e}")


def is_video_file_fine(input_file):
    try:
        with VideoFileClip(input_file) as video_clip:
            return True
    except Exception as e:
        logger.error(f"Error checking video file: {e}")
        return False


import subprocess
import json


def get_video_info(filename):
    logger.info(f"Getting video info for file: {filename}")
    try:
        # Run ffprobe command
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

        # Parse the JSON output
        probe_data = json.loads(result.stdout)

        # Find the video stream
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

        # Extract relevant information
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


def get_folder_size(folder_path):
    total_size = 0
    for dirpath, dirnames, filenames in os.walk(folder_path):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            total_size += os.path.getsize(fp)
    return total_size


def calculate_bitrate(folder_size, duration):
    # Convert folder size to bits and duration to seconds
    size_in_bits = folder_size * 8
    bitrate = size_in_bits / duration
    # Convert to kbps and round to nearest 100
    return round(bitrate / 1000 / 100) * 100


import os
import time
import shutil
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv
import json
from decimal import Decimal
import logging

import boto3
import ffmpeg
from moviepy.editor import VideoFileClip
from PIL import Image
import glob

# Set up logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# ... [previous code remains the same] ...


def get_folder_size(folder_path):
    total_size = 0
    for dirpath, dirnames, filenames in os.walk(folder_path):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            total_size += os.path.getsize(fp)
    return total_size


def calculate_bitrate(folder_size, duration):
    # Convert folder size to bits and duration to seconds
    size_in_bits = folder_size * 8
    bitrate = size_in_bits / duration
    # Convert to kbps and round to nearest 100
    return round(bitrate / 1000 / 100) * 100


def generate_hls_variants(max_width, max_height, folder_path, duration):
    variants = [
        {"name": "4k", "width": 3840, "height": 2160},
        {"name": "1440p", "width": 2560, "height": 1440},
        {"name": "1080p", "width": 1920, "height": 1080},
        {"name": "720p", "width": 1280, "height": 720},
        {"name": "480p", "width": 854, "height": 480},
    ]

    folder_size = get_folder_size(folder_path)
    original_bitrate = calculate_bitrate(folder_size, duration)

    hls_variants = []
    for variant in variants:
        if max_width >= variant["width"] or max_height >= variant["height"]:
            target_width, target_height = adjust_resolution(
                max_width, max_height, variant["width"], variant["height"]
            )
            # Calculate bitrate based on resolution ratio
            resolution_ratio = (target_width * target_height) / (max_width * max_height)
            variant_bitrate = int(original_bitrate * resolution_ratio)
            # Ensure minimum bitrate of 500 kbps
            variant_bitrate = max(variant_bitrate, 500)
            hls_variants.append(
                {
                    "playlist_name": variant["name"],
                    "resolution": f"{target_width}x{target_height}",
                    "video_bitrate": f"{variant_bitrate}k",
                    "audio_bitrate": (
                        "128k" if variant["name"] in ["1080p", "720p"] else "96k"
                    ),
                }
            )

    return hls_variants


def adjust_resolution(width, height, target_width, target_height):
    aspect_ratio = width / height
    if width > height:
        new_width = target_width
        new_height = int(round(new_width / aspect_ratio))
    else:
        new_height = target_height
        new_width = int(round(new_height * aspect_ratio))
    return new_width - (new_width % 2), new_height - (new_height % 2)


def create_adaptive_hls(input_file, output_folder):
    video_info = get_video_info(input_file)
    hls_variants = generate_hls_variants(
        video_info["width"],
        video_info["height"],
        os.path.dirname(input_file),
        video_info["duration"],
    )

    for variant in hls_variants:
        playlist_name = variant["playlist_name"]
        output_stream = f"{output_folder}/{playlist_name}/stream.m3u8"
        Path(f"{output_folder}/{playlist_name}").mkdir(parents=True, exist_ok=True)

        ffmpeg.input(input_file).output(
            output_stream,
            vf=f"scale={variant['resolution']}",
            vcodec="libx264",
            preset="veryfast",
            crf=23,
            acodec="aac",
            audio_bitrate=variant["audio_bitrate"],
            video_bitrate=variant["video_bitrate"],
            ar="48000",
            f="hls",
            hls_time=6,
            hls_playlist_type="vod",
            pix_fmt="yuv420p",
            hls_segment_filename=f"{output_folder}/{playlist_name}/%03d.ts",
        ).run()

    create_master_playlist(output_folder, hls_variants)
    generate_sprite_webvtt_and_gif(input_file, output_folder)


def create_master_playlist(output_folder, hls_variants):
    with open(f"{output_folder}/master.m3u8", "w") as f:
        f.write("#EXTM3U\n")
        for variant in hls_variants:
            video_bitrate = int(variant["video_bitrate"][:-1]) * 1000
            audio_bitrate = int(variant["audio_bitrate"][:-1]) * 1000
            f.write(
                f"#EXT-X-STREAM-INF:BANDWIDTH={video_bitrate + audio_bitrate},RESOLUTION={variant['resolution']}\n"
            )
            f.write(f"{variant['playlist_name']}/stream.m3u8\n")


def generate_sprite_webvtt_and_gif(input_file, output_dir):
    num_frames = 100
    frame_width, frame_height = 384, 216
    video_info = get_video_info(input_file)
    duration = video_info["duration"]
    fps = num_frames / duration
    frame_duration_sec = Decimal(duration) / num_frames

    ffmpeg.input(input_file).output(
        os.path.join(output_dir, "frame%03d.jpg"),
        vf=f"fps={fps},scale={frame_width}:{frame_height}",
    ).run()

    create_sprite_image(output_dir, frame_width, frame_height)
    create_webvtt_file(
        output_dir, num_frames, frame_duration_sec, frame_width, frame_height
    )
    create_gifs(output_dir, num_frames)

    for filename in glob.glob(os.path.join(output_dir, "frame*.jpg")):
        os.remove(filename)


def create_sprite_image(output_dir, frame_width, frame_height):
    images = [
        Image.open(image_file)
        for image_file in sorted(glob.glob(os.path.join(output_dir, "frame*.jpg")))
    ]
    sprite = Image.new("RGB", (10 * frame_width, 10 * frame_height))
    for i, image in enumerate(images):
        x, y = (i % 10) * frame_width, (i // 10) * frame_height
        sprite.paste(image, (x, y))
    sprite.save(os.path.join(output_dir, "sprite.jpg"))


def create_webvtt_file(
    output_dir, num_frames, frame_duration_sec, frame_width, frame_height
):
    with open(os.path.join(output_dir, "sprite.vtt"), "w") as f:
        f.write("WEBVTT\n\n")
        for i in range(num_frames):
            start_time = i * frame_duration_sec
            end_time = (i + 1) * frame_duration_sec
            x, y = (i % 10) * frame_width, (i // 10) * frame_height
            f.write(
                f"{seconds_to_hhmmss(start_time)} --> {seconds_to_hhmmss(end_time)}\n"
            )
            f.write(f"sprite.jpg#xywh={x},{y},{frame_width},{frame_height}\n\n")


def create_gifs(output_dir, num_frames):
    images = [
        Image.open(image_file)
        for image_file in sorted(glob.glob(os.path.join(output_dir, "frame*.jpg")))
    ]

    short_gif_frames = [images[i] for i in range(0, num_frames, 10)]
    short_gif_frames[0].save(
        os.path.join(output_dir, "short.gif"),
        append_images=short_gif_frames[1:],
        save_all=True,
        duration=5000,
        loop=0,
    )

    images[0].save(
        os.path.join(output_dir, "long.gif"),
        append_images=images[1:],
        save_all=True,
        duration=500,
        loop=0,
    )


def seconds_to_hhmmss(input_seconds):
    seconds = round(Decimal(input_seconds))
    return "{:02d}:{:02d}:{:02d}".format(
        seconds // 3600, (seconds % 3600) // 60, seconds % 60
    )


def upload_to_s3(local_path, relative_path, s3_client):
    try:
        s3_client.upload_file(local_path, os.getenv("AWS_BUCKET_2"), relative_path)
    except Exception as e:
        logger.error(f"Failed to upload {local_path}. Error: {str(e)}")


def delete_file_from_s3(file_name):
    s3_client = boto3.client(
        "s3",
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID_1"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY_1"),
    )
    bucket_name = os.getenv("AWS_BUCKET_1")
    try:
        s3_client.delete_object(Bucket=bucket_name, Key=file_name)
        logger.info(f"File {file_name} has been deleted from S3 bucket {bucket_name}.")
    except Exception as e:
        logger.error(f"Failed to delete file {file_name} from S3: {str(e)}")


def handler(file_name):
    try:
        setup(file_name)
        raw_file_path = f"./upload/{file_name}/{file_name}"

        s3_client = boto3.client(
            "s3",
            aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID_1"),
            aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY_1"),
        )
        s3_client.download_file(os.getenv("AWS_BUCKET_1"), file_name, raw_file_path)

        if not is_video_file_fine(raw_file_path):
            raise ValueError(f"Broken video: {file_name}")

        start = time.time()
        create_adaptive_hls(raw_file_path, f"./upload/{file_name}")
        logger.info("Adaptive Stream complete")
        log_time_taken(start)

        start = time.time()
        upload_everything()
        logger.info("Upload complete")
        log_time_taken(start)

        send_webhook(file_name, "DONE")
        s3_client.delete_object(Bucket=os.getenv("AWS_BUCKET_1"), Key=file_name)
        logger.info(f"File '{file_name}' deleted from main account.")
    except Exception as e:
        logger.error(f"Error in handler: {str(e)}")
        send_webhook(file_name, "FAILED")
    finally:
        cleanup()


def log_time_taken(start):
    end = time.time()
    duration_seconds = end - start
    minutes, seconds = divmod(int(duration_seconds), 60)
    logger.info(f"Time taken: {minutes} minutes and {seconds} seconds")


def upload_everything():
    s3_client_2 = boto3.client(
        "s3",
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID_2"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY_2"),
        endpoint_url=os.getenv("AWS_ENDPOINT_2"),
    )

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = []
        for root, dirs, files in os.walk("./upload"):
            for file in files:
                local_path = os.path.join(root, file)
                relative_path = os.path.relpath(local_path, "./upload")
                future = executor.submit(
                    upload_to_s3, local_path, relative_path, s3_client_2
                )
                futures.append(future)

        for future in futures:
            try:
                future.result()
            except Exception as e:
                logger.error(f"Error in upload_everything: {str(e)}")
                raise  # Re-raise the exception to trigger the FAILED webhook


if __name__ == "__main__":
    load_dotenv()
    main()
