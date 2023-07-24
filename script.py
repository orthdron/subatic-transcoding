import os
import pathlib
import json
import boto3
import glob
import ffmpeg
import runpod
import datetime


# Constants
SPRITES = 100
TILE_WIDTH = 384
TILE_HEIGHT = 216
TILES_X = 10
TILES_Y = 10


def create_folder_if_not_exists(dir):
    pathlib.Path(dir).mkdir(parents=True, exist_ok=True)


def transcode_video(input_file_path, resolution, bitrate, output_folder, fps):
    output_path = pathlib.Path(output_folder) / "video.m3u8"
    max_bitrate = int(bitrate * 1.07)
    buffer_size = int(bitrate * 1.5)

    cmd = (
        ffmpeg.input(input_file_path)
        .filter("scale_npp", w=-2, h=resolution)
        .output(
            output_path,
            c="h264_nvenc",
            rc="vbr_hq",
            cq=19,
            profile="main",
            b=f"{bitrate}k",
            c_aac="aac",
            hls_time=10,
            hls_playlist_type="vod",
            hls_segment_filename=str(pathlib.Path(output_folder) / "video_%d.ts"),
            maxrate=f"{max_bitrate}k",
            bufsize=f"{buffer_size}k",
            g=int(fps * 2),
            keyint_min=int(fps * 2),
        )
        .overwrite_output()
    )

    ffmpeg.run(cmd)
    print(f"Transcoding to {resolution} ({bitrate}kbps) HLS completed.")


def format_time(seconds):
    return str(datetime.timedelta(seconds=seconds))


def generate_sprite_and_vtt(
    input_file_path, output_folder, duration, fps, resolution, bitrate
):
    interval = duration / SPRITES
    frame_output_path = os.path.join(output_folder, "frame-%03d.jpg")
    sprite_output_path = os.path.join(output_folder, "sprite.jpg")
    vtt_output_path = os.path.join(output_folder, "sprite.vtt")
    gif_output_path = os.path.join(output_folder, "sprite.gif")

    # Generate individual frames
    ffmpeg.input(input_file_path).output(
        frame_output_path,
        vf=f"scale_npp=w=-2:h={resolution}",
    ).run(overwrite_output=True)
    print(f"Individual frames generated for {resolution} ({bitrate}kbps) HLS.")

    # Combine individual frames into a sprite
    ffmpeg.input(frame_output_path, framerate=fps).output(
        sprite_output_path,
        filter_complex=f"[0:v]tile={TILES_X}x{TILES_Y}:padding=0:margin=0[out]",
        map="[out]",
    ).run(overwrite_output=True)
    print(f"Sprite generated for {resolution} ({bitrate}kbps) HLS.")

    # Generate GIF from the frames
    ffmpeg.input(sprite_output_path).output(
        gif_output_path,
    ).run(overwrite_output=True)
    print(f"GIF generated for {resolution} ({bitrate}kbps) HLS.")

    # Remove individual frames
    os.remove(frame_output_path)

    # Generate VTT file
    vtt_data = ["WEBVTT"]
    grid_size = 10  # Your grid size
    for i in range(SPRITES):
        start_time = format_time(i * interval)
        end_time = format_time((i + 1) * interval)
        x = (i % grid_size) * TILE_WIDTH  # Modulus operator to loop x
        y = (i // grid_size) * TILE_HEIGHT  # Increment y after each row
        vtt_data.extend(
            [
                "",
                f"{start_time} --> {end_time}",
                f"sprite.jpg#xywh={x},{y},{TILE_WIDTH},{TILE_HEIGHT}",
            ]
        )

    with open(vtt_output_path, "w") as f:
        f.write("\n".join(vtt_data))

    print("Sprite, VTT, and GIF generated.")


def transcode_to_all_resolutions(input_file_path, output_folder, fps, duration):
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
                input_file_path, r["resolution"], r["bitrate"], resolution_folder, fps
            )
            generate_sprite_and_vtt(
                input_file_path,
                resolution_folder,
                duration,
                fps,
                r["resolution"],
                r["bitrate"],
            )

    master_playlist_path = pathlib.Path(output_folder) / "master.m3u8"
    with open(master_playlist_path, "w") as f:
        f.write("\n".join(master_playlist))
    print("Master playlist (master.m3u8) created.")


def get_input_video_resolution(input_file_path):
    probe_data = ffmpeg.probe(
        input_file_path,
        v="error",
        select_streams="v:0",
        show_entries="stream=width,height",
    )
    return {
        "width": probe_data["streams"][0]["width"],
        "height": probe_data["streams"][0]["height"],
    }


def get_video_frame_rate(input_file_path):
    probe_data = ffmpeg.probe(
        input_file_path, v="error", show_entries="stream=r_frame_rate"
    )
    num, den = probe_data["streams"][0]["r_frame_rate"].split("/")
    return int(num) / int(den)


def get_resolutions(fps):
    return (
        [
            {"name": "2160p", "resolution": "3840x2160", "bitrate": 45000},  # 45 Mbps
            {"name": "1440p", "resolution": "2560x1440", "bitrate": 16000},  # 16 Mbps
            {"name": "1080p", "resolution": "1920x1080", "bitrate": 8000},  # 8 Mbps
            {"name": "720p", "resolution": "1280x720", "bitrate": 5000},  # 5 Mbps
            {"name": "480p", "resolution": "854x480", "bitrate": 2500},  # 2.5 Mbps
            {"name": "360p", "resolution": "640x360", "bitrate": 1000},  # 1 Mbps
            {"name": "240p", "resolution": "426x240", "bitrate": 750},  # 750 Kbps
        ]
        if fps <= 30
        else [
            {"name": "2160p", "resolution": "3840x2160", "bitrate": 68000},  # 68 Mbps
            {"name": "1440p", "resolution": "2560x1440", "bitrate": 24000},  # 24 Mbps
            {"name": "1080p", "resolution": "1920x1080", "bitrate": 12000},  # 12 Mbps
            {"name": "720p", "resolution": "1280x720", "bitrate": 7500},  # 7.5 Mbps
            {"name": "480p", "resolution": "854x480", "bitrate": 4000},  # 4 Mbps
            {"name": "360p", "resolution": "640x360", "bitrate": 1500},  # 1.5 Mbps
            {"name": "240p", "resolution": "426x240", "bitrate": 1000},  # 1 Mbps
        ]
    )


def get_video_duration(input_file_path):
    probe_data = ffmpeg.probe(
        input_file_path, v="error", show_entries="format=duration"
    )
    return float(probe_data["format"]["duration"])


def handler(event):
    job_input = event["input"]
    print(event)
    file_name = job_input["file"]
    fps = get_video_frame_rate(file_name)
    output_folder = pathlib.Path(file_name).parent / pathlib.Path(file_name).stem

    s3_client = boto3.client(
        "s3",
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID_1"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY_1"),
    )
    s3_client.download_file(os.getenv("AWS_BUCKET_1"), file_name, f"/tmp/{file_name}")

    try:
        input_file_path = "/tmp/" + file_name
        duration = get_video_duration(input_file_path)
        transcode_to_all_resolutions(input_file_path, output_folder, fps, duration)

        # Upload the output folder to a different s3 compatible storage
        s3_client_2 = boto3.client(
            "s3",
            aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID_2"),
            aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY_2"),
            endpoint_url=os.getenv("AWS_ENDPOINT_2"),
        )
        for file_name in glob.glob(output_folder + "/*"):
            s3_client_2.upload_file(file_name, os.getenv("AWS_BUCKET_2"), file_name)

        return "Processing complete"
    except Exception as e:
        return f"Error: {e}"


runpod.serverless.start({"handler": handler})
