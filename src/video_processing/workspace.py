import os
import shutil
from dataclasses import dataclass

from src.logging_config import logger

WORK_ROOT = "./upload"


@dataclass(frozen=True)
class Workspace:
    """Local folders for one job.

    Only `output` is uploaded. The raw source lives outside it so it can never
    end up in the public processed bucket.
    """

    root: str
    source: str  # path of the downloaded raw file
    output: str  # everything under here is published as <video_id>/...
    frames: str  # temporary thumbnail frames


def create_workspace(video_id):
    if not video_id or video_id in (".", "..") or "/" in video_id or "\\" in video_id:
        raise ValueError(f"Invalid video id: {video_id!r}")
    root = os.path.join(WORK_ROOT, video_id)
    workspace = Workspace(
        root=root,
        source=os.path.join(root, "source", video_id),
        output=os.path.join(root, "output"),
        frames=os.path.join(root, "frames"),
    )
    for folder in (os.path.dirname(workspace.source), workspace.output, workspace.frames):
        os.makedirs(folder, exist_ok=True)
    logger.info(f"Workspace ready at {root}")
    return workspace


def cleanup():
    """Remove all local job files (the worker runs one job at a time)."""
    if not os.path.exists(WORK_ROOT):
        return
    try:
        shutil.rmtree(WORK_ROOT)
        logger.info(f"Removed {WORK_ROOT}")
    except OSError as e:
        logger.error(f"Could not remove {WORK_ROOT}: {e}")
