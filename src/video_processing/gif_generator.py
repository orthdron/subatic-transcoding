import os
import glob
from PIL import Image
from src.logging_config import logger


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

    middle_index = len(images) // 2
    middle_image = images[middle_index]
    middle_image.save(os.path.join(output_dir, "poster.jpg"))

    logger.info("GIFs and poster image created successfully.")
