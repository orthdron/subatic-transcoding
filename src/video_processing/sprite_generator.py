import os
import glob
from decimal import Decimal
import ffmpeg
from PIL import Image
from src.logging_config import logger
from src.video_processing.gif_generator import create_gifs
from .video_info import get_video_info


def generate_sprite_and_vtt(input_file, output_dir):
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


def seconds_to_hhmmss(input_seconds):
    seconds = round(Decimal(input_seconds))
    return "{:02d}:{:02d}:{:02d}".format(
        seconds // 3600, (seconds % 3600) // 60, seconds % 60
    )
