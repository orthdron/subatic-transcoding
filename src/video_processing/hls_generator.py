import os
import ffmpeg
from src.logging_config import logger
from src.video_processing.sprite_generator import generate_sprite_and_vtt
from src.video_processing.video_info import get_video_info


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
            resolution_ratio = (target_width * target_height) / (max_width * max_height)
            variant_bitrate = int(original_bitrate * resolution_ratio)
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
        os.makedirs(f"{output_folder}/{playlist_name}", exist_ok=True)

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
    generate_sprite_and_vtt(input_file, output_folder)

    return video_info["duration"]


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


def adjust_resolution(width, height, target_width, target_height):
    aspect_ratio = width / height
    if width > height:
        new_width = target_width
        new_height = int(round(new_width / aspect_ratio))
    else:
        new_height = target_height
        new_width = int(round(new_height * aspect_ratio))
    return new_width - (new_width % 2), new_height - (new_height % 2)
