"""
FFmpeg integration for frame extraction.

Provides generator functions that yield raw RGB24 frame bytes from a video
source using FFmpeg as the decoder.  Each frame is exactly
``width × height × 3`` bytes (RGB24, row-major, top-to-bottom, no padding).
"""

import json
import subprocess
import sys
from typing import Generator, Optional, Tuple


def get_video_info(source: str) -> Tuple[int, int, float]:
    """
    Probe a video source and return its dimensions and frame rate.

    Args:
        source: File path, device, or URL understood by ffprobe.

    Returns:
        ``(width, height, fps)`` tuple.

    Raises:
        :exc:`subprocess.CalledProcessError` if ffprobe fails.
    """
    cmd = [
        "ffprobe",
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height,r_frame_rate",
        "-of", "json",
        source,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    data = json.loads(result.stdout)
    stream = data["streams"][0]
    width = int(stream["width"])
    height = int(stream["height"])
    num, den = map(int, stream["r_frame_rate"].split("/"))
    fps = num / den
    return width, height, fps


def extract_frames(
    source: str,
    width: Optional[int] = None,
    height: Optional[int] = None,
    start_frame: int = 0,
    max_frames: Optional[int] = None,
) -> Generator[bytes, None, None]:
    """
    Yield raw RGB24 frame bytes from *source* via FFmpeg.

    Args:
        source:      Video file path, device path, URL, or ``"-"`` for stdin.
        width:       Override output frame width; uses native width if omitted.
        height:      Override output frame height; uses native height if omitted.
        start_frame: Skip this many frames at the beginning of the stream.
        max_frames:  Stop after this many frames (``None`` for all frames).

    Yields:
        :class:`bytes` of length ``width × height × 3`` per frame (RGB24).
    """
    if width is None or height is None:
        probe_w, probe_h, _ = get_video_info(source)
        if width is None:
            width = probe_w
        if height is None:
            height = probe_h

    frame_size = width * height * 3

    cmd = ["ffmpeg", "-v", "error", "-i", source]

    if start_frame > 0:
        cmd += ["-vf", f"select=gte(n\\,{start_frame})"]

    if max_frames is not None:
        cmd += ["-frames:v", str(max_frames)]

    cmd += [
        "-f", "rawvideo",
        "-pix_fmt", "rgb24",
        "-",
    ]

    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        while True:
            chunk = proc.stdout.read(frame_size)
            if len(chunk) == 0:
                break
            if len(chunk) < frame_size:
                # Partial final frame – discard
                break
            yield chunk
    finally:
        proc.stdout.close()
        proc.wait()
        if proc.returncode not in (0, None):
            stderr = proc.stderr.read().decode("utf-8", errors="replace")
            if stderr.strip():
                print(f"ffmpeg: {stderr.strip()}", file=sys.stderr)


def frames_from_stdin(
    width: int,
    height: int,
) -> Generator[bytes, None, None]:
    """
    Yield raw RGB24 frame bytes piped to stdin.

    Intended for use in a pipeline such as::

        ffmpeg ... -f rawvideo -pix_fmt rgb24 - | python fingerprint_video.py --stdin ...

    Args:
        width:  Expected frame width in pixels.
        height: Expected frame height in pixels.

    Yields:
        :class:`bytes` of length ``width × height × 3`` per frame (RGB24).
    """
    frame_size = width * height * 3
    while True:
        chunk = sys.stdin.buffer.read(frame_size)
        if len(chunk) == 0:
            break
        if len(chunk) < frame_size:
            break
        yield chunk
