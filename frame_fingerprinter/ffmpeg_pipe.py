"""
FFmpeg integration for frame extraction.

Provides generator functions that yield raw RGB24 frame bytes from a video
source using FFmpeg as the decoder.  Each frame is exactly
``width × height × 3`` bytes (RGB24, row-major, top-to-bottom, no padding).
"""

import json
import subprocess
import sys
import threading
from typing import Generator, Optional, Tuple

__all__ = [
    "get_video_info",
    "extract_frames",
    "frames_from_stdin",
]


def _drain_stderr(proc: subprocess.Popen) -> str:
    """Read and return all remaining stderr from *proc* without deadlocking.

    Runs in a daemon thread so it does not block the caller.  Returns the
    collected output once the process has exited.
    """
    chunks: list[bytes] = []

    def _reader() -> None:
        if proc.stderr:
            chunks.append(proc.stderr.read())

    t = threading.Thread(target=_reader, daemon=True)
    t.start()
    proc.wait()
    t.join(timeout=5)
    return b"".join(chunks).decode("utf-8", errors="replace")


def get_video_info(source: str) -> Tuple[int, int, float]:
    """
    Probe a video source and return its dimensions and frame rate.

    Args:
        source: File path, device, or URL understood by ffprobe.

    Returns:
        ``(width, height, fps)`` tuple.

    Raises:
        :exc:`subprocess.CalledProcessError` if ffprobe fails.
        :exc:`ValueError` if the source contains no video stream.
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
    streams = data.get("streams", [])
    if not streams:
        raise ValueError(f"No video stream found in '{source}'")
    stream = streams[0]
    width = int(stream["width"])
    height = int(stream["height"])
    num, den = map(int, stream["r_frame_rate"].split("/"))
    fps = num / max(den, 1)
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
    stderr_text = ""
    try:
        assert proc.stdout is not None
        while True:
            chunk = proc.stdout.read(frame_size)
            if len(chunk) == 0:
                break
            if len(chunk) < frame_size:
                # Partial final frame – discard silently
                break
            yield chunk
    finally:
        if proc.stdout:
            proc.stdout.close()
        # Drain stderr concurrently with proc.wait() to avoid deadlock when
        # ffmpeg writes a large error message and fills the pipe buffer.
        stderr_text = _drain_stderr(proc)

    if proc.returncode not in (0, None) and stderr_text.strip():
        print(f"ffmpeg: {stderr_text.strip()}", file=sys.stderr)


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
