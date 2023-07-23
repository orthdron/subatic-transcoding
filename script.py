import os
import subprocess
import pathlib
import json
import boto3
import glob
import ffmpeg
import runpod
import datetime


def create_folder_if_not_exists(dir):
    pathlib.Path(dir).mkdir(parents=True, exist_ok=True)


def transcode_video(input_file_path, resolution, bitrate, output_folder):
    output_path = pathlib.Path(output_folder) / "video.m3u8"
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        input_file_path,
        "-vf",
        f"scale={resolution}",
        "-c:v",
        "h264_nvenc",
        "-b:v",
        f"{bitrate}k",
        "-c:a",
        "aac",
        "-hls_time",
        "10",
        "-hls_playlist_type",
        "vod",
        "-hls_segment_filename",
        str(pathlib.Path(output_folder) / "video_%d.ts"),
        str(output_path),
    ]
    subprocess.run(cmd, check=True)
    print(f"Transcoding to {resolution} ({bitrate}kbps) HLS completed.")


def format_time(seconds):
    return str(datetime.timedelta(seconds=seconds))


def generate_sprite_and_vtt(input_file_path, output_folder, duration):
    sprites = 100
    tile_width = 384
    tile_height = 216
    tiles_x = 10
    tiles_y = 10
    interval = duration / sprites
    frame_output_path = os.path.join(output_folder, "frame-%03d.jpg")
    sprite_output_path = os.path.join(output_folder, "sprite.jpg")
    vtt_output_path = os.path.join(output_folder, "sprite.vtt")
    gif_output_path = os.path.join(output_folder, "sprite.gif")

    # Generate individual frames
    cmd = [
        "ffmpeg",
        "-i",
        input_file_path,
        "-vf",
        f"fps=1/{interval},scale={tile_width}:{tile_height}",
        "-frames",
        str(sprites),
        frame_output_path,
    ]
    subprocess.run(cmd, check=True)

    # Combine individual frames into a sprite
    cmd = [
        "ffmpeg",
        "-i",
        frame_output_path,
        "-filter_complex",
        f"tile={tiles_x}x{tiles_y}",
        sprite_output_path,
    ]
    subprocess.run(cmd, check=True)

    # Generate GIF from the frames
    cmd = [
        "ffmpeg",
        "-i",
        frame_output_path,
        "-vf",
        f"fps=2,scale={tile_width}:{tile_height}",
        gif_output_path,
    ]
    subprocess.run(cmd, check=True)

    # Remove individual frames
    cmd = ["rm", f"{output_folder}/frame-*.jpg"]
    subprocess.run(cmd, shell=True, check=True)

    # Generate VTT file
    vtt_data = ["WEBVTT"]
    grid_size = 10  # Your grid size
    for i in range(sprites):
        start_time = format_time(i * interval)
        end_time = format_time((i + 1) * interval)
        x = (i % grid_size) * tile_width  # Modulus operator to loop x
        y = (i // grid_size) * tile_height  # Increment y after each row
        vtt_data.extend(
            [
                "",
                f"{start_time} --> {end_time}",
                f"sprite.jpg#xywh={x},{y},{tile_width},{tile_height}",
            ]
        )

    with open(vtt_output_path, "w") as f:
        f.write("\n".join(vtt_data))

    print("Sprite, VTT, and GIF generated.")


def transcode_to_all_resolutions(input_file_path, output_folder, fps, duration):
    generate_sprite_and_vtt(input_file_path, output_folder, duration)
    input_file_name = pathlib.Path(input_file_path).stem
    input_resolution = get_input_video_resolution(input_file_path)
    resolutions = get_resolutions(fps)
    create_folder_if_not_exists(output_folder)
    master_playlist = ["#EXTM3U"]

    for r in resolutions:
        if input_resolution["width"] >= int(r["resolution"].split("x")[0]):
            resolution_folder = pathlib.Path(output_folder) / r["name"]
            create_folder_if_not_exists(resolution_folder)
            master_playlist.append(
                f'#EXT-X-STREAM-INF:BANDWIDTH={r["bitrate"]}000,RESOLUTION={r["resolution"]}'
            )
            master_playlist.append(f'{r["name"]}/video.m3u8')
            transcode_video(
                input_file_path, r["resolution"], r["bitrate"], resolution_folder
            )
            master_playlist_path = pathlib.Path(output_folder) / "master.m3u8"
            with open(master_playlist_path, "w") as f:
                f.write("\n".join(master_playlist))
            print("Master playlist (master.m3u8) created.")


def get_input_video_resolution(input_file_path):
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height",
        "-of",
        "json",
        input_file_path,
    ]
    output = subprocess.run(cmd, text=True, capture_output=True, check=True)
    data = json.loads(output.stdout)
    return {
        "width": data["streams"][0]["width"],
        "height": data["streams"][0]["height"],
    }


def get_video_frame_rate(input_file_path):
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        "-show_entries",
        "stream=r_frame_rate",
        input_file_path,
    ]
    output = subprocess.run(cmd, text=True, capture_output=True, check=True)
    num, den = output.stdout.split("/")
    return int(num) / int(den)


def get_resolutions(fps):
    return (
        [
            {"name": "2160p", "resolution": "3840x2160", "bitrate": 45000},
            {"name": "1440p", "resolution": "2560x1440", "bitrate": 16000},
            {"name": "1080p", "resolution": "1920x1080", "bitrate": 8000},
            {"name": "720p", "resolution": "1280x720", "bitrate": 5000},
            {"name": "480p", "resolution": "854x480", "bitrate": 2500},
            {"name": "360p", "resolution": "640x360", "bitrate": 1000},
            {"name": "240p", "resolution": "426x240", "bitrate": 700},
        ]
        if fps <= 30
        else [
            {"name": "2160p", "resolution": "3840x2160", "bitrate": 68000},
            {"name": "1440p", "resolution": "2560x1440", "bitrate": 24000},
            {"name": "1080p", "resolution": "1920x1080", "bitrate": 12000},
            {"name": "720p", "resolution": "1280x720", "bitrate": 7500},
            {"name": "480p", "resolution": "854x480", "bitrate": 4000},
            {"name": "360p", "resolution": "640x360", "bitrate": 3000},
            {"name": "240p", "resolution": "426x240", "bitrate": 2250},
        ]
    )


def get_video_duration(input_file_path):
    return float(ffmpeg.probe(input_file_path)["format"]["duration"])


def handler(event):
    print(event)
    file_name = event.file
    fps = get_video_frame_rate(input_file_path)
    output_folder = (
        pathlib.Path(input_file_path).parent / pathlib.Path(input_file_path).stem
    )
    # Download the file from AWS account 1 to /tmp/{event.file}
    s3_client = boto3.client(
        "s3",
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID_1"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY_1"),
        aws_session_token=os.getenv("AWS_SESSION_TOKEN_1"),  # if needed
    )
    s3_client.download_file("your_bucket_name", file_name, f"/tmp/{file_name}")

    try:
        input_file_path = "/tmp/" + event.file
        duration = get_video_duration(input_file_path)
        transcode_to_all_resolutions(input_file_path, output_folder, fps, duration)

        # Upload the output folder to a different s3 compatible storage
        s3_client_2 = boto3.client(
            "s3",
            aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID_2"),
            aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY_2"),
            aws_session_token=os.getenv("AWS_SESSION_TOKEN_2"),  # if needed
            endpoint_url="https://your-endpoint-url",  # URL for your S3-compatible storage
        )
        for file_name in glob.glob(output_folder + "/*"):
            s3_client_2.upload_file(file_name, "your_bucket_name", file_name)

        return "Processing complete"
    except Exception as e:
        return f"Error: {e}"


runpod.serverless.start({"handler": handler})