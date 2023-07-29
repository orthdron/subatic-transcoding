import os
import time
import shutil
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv
import json
from decimal import Decimal

import boto3
import ffmpeg
from moviepy.editor import VideoFileClip
from PIL import Image
import glob


def main():
    load_dotenv()
    sqs_session = boto3.Session(
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID_1"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY_1"),
        region_name=os.getenv("AWS_REGION"),
    )

    sqs_client = sqs_session.client("sqs")

    queue_url = os.getenv("AWS_SQS_URL")

    response = sqs_client.receive_message(
        QueueUrl=queue_url, MaxNumberOfMessages=1, WaitTimeSeconds=20
    )
    messages = response.get("Messages", [])
    if not messages:
        print("No messages in the queue. Waiting...")
        return

    message = messages[0]

    message_data = message.get("Body")
    if message_data:
        print("Received this message")
        print(message_data)
        try:
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
                            print("Error processing message:", str(e))
                    else:
                        print(message_data)
        except Exception as e:
            print("Error parsing message:", str(e))

    print("Sleeping for 5 seconds...")
    time.sleep(5)

    # Delete the processed message from the queue
    sqs_client.delete_message(
        QueueUrl=queue_url, ReceiptHandle=message["ReceiptHandle"]
    )


def setup(file_name):
    cleanup()
    folder_path = "./upload/" + file_name
    try:
        Path(folder_path).mkdir(parents=True, exist_ok=True)
        print(f"Folder '{folder_path}' created successfully.")
    except FileExistsError:
        print(f"Folder '{folder_path}' already exists.")
    except Exception as e:
        print(f"Error occurred while creating folder: {e}")


def remove_files_with_wildcard(file_pattern):
    files_to_remove = glob.glob(file_pattern)

    if not files_to_remove:
        print(f"No files found matching the pattern '{file_pattern}'.")
        return

    for file_path in files_to_remove:
        if os.path.exists(file_path):
            os.remove(file_path)
            print(f"File '{file_path}' has been removed.")
        else:
            print(f"File '{file_path}' does not exist.")


def cleanup():
    folder_path = "./upload/"
    try:
        remove_files_with_wildcard("./input*")
        shutil.rmtree(folder_path)
        print(f"Folder '{folder_path}' and its contents removed successfully.")
    except FileNotFoundError:
        print(f"Folder '{folder_path}' not found.")
    except OSError as e:
        print(f"Error occurred while removing folder and its contents: {e}")


def is_video_file_fine(input_file):
    try:
        video_clip = VideoFileClip(input_file)
        video_clip.reader.close()  # Close the clip to release resources
        return True
    except Exception as e:
        print(f"Error: {e}")
        return False


def notify_broken_video(file_name):
    print("Broken video")
    return


def notify_failure(file_name):
    print("We failed to do so")
    return


def get_video_duration(filename):
    probe = ffmpeg.probe(filename)
    video_info = next(
        (stream for stream in probe["streams"] if stream["codec_type"] == "video"), None
    )
    if video_info is None:
        raise Exception("No video stream found")

    return float(video_info["duration"])


def preprocess_video(input_file, output_file):
    video_clip = VideoFileClip(input_file)
    original_bitrate = get_video_bitrate(input_file)
    # Resize the video to have a maximum width of 3840 and maximum height of 2160
    resized_clip = video_clip
    if video_clip.w > 3840 or video_clip.h > 2160:
        original_aspect_ratio = video_clip.w / video_clip.h
        target_aspect_ratio = 3840 / 2160

        if original_aspect_ratio > target_aspect_ratio:
            # Resize to fit the width to 3840 and maintain aspect ratio
            video_clip = video_clip.resize(width=3840)
        else:
            # Resize to fit the height to 2160 and maintain aspect ratio
            video_clip = video_clip.resize(height=2160)

    # Set the video frame rate to 60 frames per second
    fps = video_clip.fps
    if fps > 60:
        fps = 60

    final_duration = resized_clip.duration / resized_clip.fps * fps
    final_clip = resized_clip.set_duration(final_duration).set_fps(fps)
    final_bitrate = 16000
    if original_bitrate < final_bitrate:
        final_bitrate = original_bitrate
    try:
        # Export the video with the specified settings
        final_clip.write_videofile(
            output_file,
            codec="libx264",
            audio_codec="aac",
            preset="medium",
            audio_bitrate="320k",
            bitrate=f"{final_bitrate}k",
            audio_fps=48000,
        )
        print("Trying")
    except Exception as error:
        print("An exception occurred:", error)
    finally:
        # Close the clips to release resources
        resized_clip.reader.close()
        resized_clip.audio.reader.close_proc()
        final_clip.reader.close()
        final_clip.audio.reader.close_proc()


def get_video_dimensions(input_file):
    probe = ffmpeg.probe(input_file, v="error")
    video_info = next(s for s in probe["streams"] if s["codec_type"] == "video")
    width = int(video_info["width"])
    height = int(video_info["height"])
    return width, height


def get_video_bitrate(input_file):
    probe = ffmpeg.probe(
        input_file, v="error", select_streams="v:0", show_entries="stream=bit_rate"
    )
    return int(probe["format"]["bit_rate"]) // 1000


def generate_hls_variants(max_width, max_height, original_bitrate):
    hls_variants = []

    def add_variant(playlist_name, resolution, video_bitrate, audio_bitrate):
        nonlocal original_bitrate
        if original_bitrate < video_bitrate:
            video_bitrate = original_bitrate
        video_bitrate_str = f"{video_bitrate}k"
        hls_variants.append(
            {
                "playlist_name": playlist_name,
                "resolution": resolution,
                "video_bitrate": video_bitrate_str,
                "audio_bitrate": audio_bitrate,
            }
        )

    def adjust_resolution(width, height, target_width, target_height):
        original_aspect_ratio = width / height

        # If original width is greater than height, fit width to target width
        if width > height:
            width = target_width
            height = int(round(width / original_aspect_ratio))
        else:
            # Otherwise, fit height to target height
            height = target_height
            width = int(round(height * original_aspect_ratio))

        # Ensure the values are even
        width = width if width % 2 == 0 else width - 1
        height = height if height % 2 == 0 else height - 1

        return width, height

    if max_width >= 3840 or max_height >= 2160:
        target_width, target_height = adjust_resolution(
            max_width, max_height, 3840, 2160
        )
        add_variant("4k", f"{target_width}x{target_height}", 16000, "320k")

    if max_width >= 2560 or max_height >= 1440:
        target_width, target_height = adjust_resolution(
            max_width, max_height, 2560, 1440
        )
        add_variant("1440p", f"{target_width}x{target_height}", 8000, "256k")

    if max_width >= 1920 or max_height >= 1080:
        target_width, target_height = adjust_resolution(
            max_width, max_height, 1920, 1080
        )
        add_variant("1080p", f"{target_width}x{target_height}", 5000, "128k")

    if max_width >= 1280 or max_height >= 720:
        target_width, target_height = adjust_resolution(
            max_width, max_height, 1280, 720
        )
        add_variant("720p", f"{target_width}x{target_height}", 2500, "128k")

    if max_width >= 854 or max_height >= 480:
        target_width, target_height = adjust_resolution(max_width, max_height, 854, 480)
        add_variant("480p", f"{target_width}x{target_height}", 1250, "96k")

    # if max_width >= 640 or max_height >= 360:
    #     target_width, target_height = adjust_resolution(max_width, max_height, 640, 360)
    #     add_variant("360p", f"{target_width}x{target_height}", 750, "64k")

    # if max_width >= 426 or max_height >= 240:
    #     target_width, target_height = adjust_resolution(max_width, max_height, 426, 240)
    #     add_variant("240p", f"{target_width}x{target_height}", 400, "48k")

    return hls_variants


def create_adaptive_hls(input_file, output_folder):
    max_width, max_height = get_video_dimensions(input_file)
    original_bitrate = get_video_bitrate(input_file)

    hls_variants = generate_hls_variants(max_width, max_height, original_bitrate)

    for idx, variant in enumerate(hls_variants):
        playlist_name = variant["playlist_name"]
        video_bitrate = variant["video_bitrate"]
        abitrate = variant["audio_bitrate"]
        resolution = variant["resolution"]
        output_stream = f"{output_folder}/{playlist_name}/stream.m3u8"
        Path(f"{output_folder}/{playlist_name}").mkdir(parents=True, exist_ok=True)
        if idx == 0:
            first_stream = output_stream
            ffmpeg.input(input_file).output(
                output_stream,
                vf=f"scale={resolution}",
                vcodec="libx264",
                preset="veryfast",
                crf=23,
                acodec="aac",
                audio_bitrate=abitrate,
                ar="48000",
                f="hls",
                hls_time=6,
                hls_playlist_type="vod",
                hls_segment_filename=f"{output_folder}/{playlist_name}/%03d.ts",
            ).run()
        else:
            prev_stream = hls_variants[idx - 1]
            prev_playlist_name = prev_stream["playlist_name"]
            ffmpeg.input(f"{output_folder}/{prev_playlist_name}/stream.m3u8").output(
                output_stream,
                vf=f"scale={resolution}:flags=lanczos",
                vcodec="libx264",
                preset="veryfast",
                crf=23,
                acodec="aac",
                audio_bitrate=abitrate,
                ar="48000",
                f="hls",
                hls_time=6,
                hls_playlist_type="vod",
                hls_segment_filename=f"{output_folder}/{playlist_name}/%03d.ts",
            ).run()

    with open(f"{output_folder}/master.m3u8", "w") as f:
        f.write("#EXTM3U\n")
        for idx, variant in enumerate(hls_variants):
            video_bitrate = variant["video_bitrate"][:-1]
            audio_bitrate = variant["audio_bitrate"][:-1]
            playlist_name = variant["playlist_name"]
            resolution = variant["resolution"]

            f.write(
                f"#EXT-X-STREAM-INF:BANDWIDTH={int(video_bitrate)*1000+int(audio_bitrate)*1000},RESOLUTION={resolution}\n"
            )
            f.write(f"{playlist_name}/stream.m3u8\n")

    generate_sprite_webvtt_and_gif(first_stream, output_folder)


def seconds_to_hhmmss(input):
    seconds = round(Decimal(input))
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    seconds = seconds % 60

    return "{:02d}:{:02d}:{:02d}".format(hours, minutes, seconds)


def generate_sprite_webvtt_and_gif(input_file, output_dir):
    num_frames = 100
    frame_width = 384
    frame_height = 216
    sprite_width = num_frames * frame_width
    sprite_height = frame_height

    # Get the total duration of the video in seconds
    probe = ffmpeg.probe(input_file)
    duration = float(probe["format"]["duration"])
    print(f"Duration: {duration}")

    # Calculate the duration of each frame in seconds
    fps = num_frames / duration
    frame_duration_sec = Decimal(duration) / num_frames

    # Extract individual frames and save them as images with the specified resolution
    (
        ffmpeg.input(input_file)
        .output(
            os.path.join(output_dir, "frame%03d.jpg"),
            vf=f"fps={fps},scale={frame_width}:{frame_height}",
        )
        .run()
    )

    # Concatenate frames into a grid (10x10) to create a sprite image
    # In Python, we'll use the Pillow library to create the sprite
    images = [
        Image.open(image_file)
        for image_file in sorted(glob.glob(os.path.join(output_dir, "frame*.jpg")))
    ]
    sprite = Image.new("RGB", (10 * frame_width, 10 * frame_height))
    for i, image in enumerate(images):
        x = (i % 10) * frame_width
        y = (i // 10) * frame_height
        sprite.paste(image, (x, y))
    sprite.save(os.path.join(output_dir, "sprite.jpg"))

    # Create the WebVTT file with the appropriate content
    webvtt_file = os.path.join(output_dir, "sprite.vtt")
    with open(webvtt_file, "w") as f:
        f.write("WEBVTT\n\n")

        # Loop through the number of frames to add captions with timestamps
        for i in range(num_frames):
            start_time = i * frame_duration_sec
            end_time = (i + 1) * frame_duration_sec

            start_time_formatted = seconds_to_hhmmss(start_time)
            end_time_formatted = seconds_to_hhmmss(end_time)

            # Calculate the frame's position in the sprite
            row = i // 10
            col = i % 10

            # Calculate the frame's coordinates in the sprite
            x = col * frame_width
            y = row * frame_height

            # Write the caption entry to the WebVTT file
            f.write(f"{start_time_formatted} --> {end_time_formatted}\n")
            f.write(
                f"sprite.jpg#xywh={x},{y},{frame_width},{frame_height}\n\n"
            )  # Add coordinates and size to the cue settings line

    short_gif_frames = [images[i] for i in range(0, num_frames, 10)]
    short_gif_frames[0].save(
        os.path.join(output_dir, "short.gif"),
        append_images=short_gif_frames[1:],
        save_all=True,
        duration=100,  # 10 fps
        loop=0,
    )

    # Create the GIF from the individual frame files using ImageMagick
    images[0].save(
        os.path.join(output_dir, "long.gif"),
        append_images=images[1:],
        save_all=True,
        duration=100,  # 10 fps
        loop=0,
    )
    # Delete all 'frame*.jpg' files in the output directory
    for filename in glob.glob(os.path.join(output_dir, "frame*.jpg")):
        os.remove(filename)


def upload_to_s3(local_path, relative_path, s3_client):
    try:
        s3_client.upload_file(local_path, os.getenv("AWS_BUCKET_2"), relative_path)
        # print(f"Uploaded {local_path} to S3")
    except Exception as e:
        print(f"Failed to upload {local_path}. Error: {str(e)}")


def handler(file_name):
    setup(file_name)
    raw_file_path = f"./upload/{file_name}/{file_name}"
    preprocessed_file_path = "./input.mp4"

    s3_client = boto3.client(
        "s3",
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID_1"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY_1"),
    )
    s3_client.download_file(os.getenv("AWS_BUCKET_1"), file_name, raw_file_path)

    if not is_video_file_fine(raw_file_path):
        cleanup()
        notify_broken_video(file_name)
        return

    # try:
    #     preprocess_video(raw_file_path, preprocessed_file_path)
    # except Exception as e:
    #     print(e)
    #     cleanup()
    #     notify_failure(file_name)
    #     return

    start = time.time()
    create_adaptive_hls(raw_file_path, f"./upload/{file_name}")
    print("Adaptive Stream complete")
    timeit(start)

    start = time.time()
    upload_everything()
    print("Upload complete")
    timeit(start)
    cleanup()


def timeit(start):
    end = time.time()
    duration_seconds = end - start
    minutes = int(duration_seconds // 60)
    seconds = int(duration_seconds % 60)

    print(f"Time taken: {minutes} minutes and {seconds} seconds")


def upload_everything():
    # Upload the output folder to a different s3 compatible storage
    s3_client_2 = boto3.client(
        "s3",
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID_2"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY_2"),
        endpoint_url=os.getenv("AWS_ENDPOINT_2"),
    )

    # Use ThreadPoolExecutor for multi-threaded file upload
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

        # Wait for all upload tasks to complete
        for future in futures:
            future.result()


if __name__ == "__main__":
    load_dotenv()
    main()
    # input_file = sys.argv[1]
    # handler(input_file)
