#!/usr/bin/env python3
"""
fingerprint_video.py – Fingerprint a video file and produce a .fpchain sidecar.

The tool processes every video frame, computes a cryptographic fingerprint that
binds each frame to its predecessor and successor (via hash chaining and
next-frame qualifying properties), then signs the fingerprint with a GnuPG key.
All fingerprints are written to a JSON Lines ``.fpchain`` file that travels with
the video.

Usage (file mode):
    python fingerprint_video.py -i dashcam.mp4 -k KEY_ID [-o output.fpchain]

Usage (stdin / pipeline mode):
    ffmpeg ... -f rawvideo -pix_fmt rgb24 - |
        python fingerprint_video.py --stdin --width 1280 --height 720 -k KEY_ID

Environment variables:
    GPG_PASSPHRASE   GPG key passphrase (alternative to --passphrase).
"""

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from frame_fingerprinter.chain import ChainWriter
from frame_fingerprinter.ffmpeg_pipe import (
    extract_frames,
    frames_from_stdin,
    get_video_info,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Fingerprint a video file frame-by-frame, producing a signed "
            ".fpchain sidecar file."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split("Usage")[1] if "Usage" in __doc__ else "",
    )

    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--input", "-i", metavar="FILE", help="Input video file")
    src.add_argument(
        "--stdin",
        action="store_true",
        help="Read raw RGB24 frames from stdin (requires --width and --height)",
    )

    parser.add_argument(
        "--key", "-k",
        required=True,
        metavar="KEY_ID",
        help="GPG key fingerprint or key ID used for signing",
    )
    parser.add_argument(
        "--output", "-o",
        metavar="FILE",
        help="Output .fpchain file (default: <input>.fpchain or stream.fpchain)",
    )
    parser.add_argument(
        "--passphrase",
        metavar="PASS",
        help="GPG key passphrase (prefer the GPG_PASSPHRASE environment variable)",
    )
    parser.add_argument("--gpg-home", metavar="DIR", help="GPG home directory")
    parser.add_argument(
        "--width", type=int, metavar="W",
        help="Frame width in pixels (required with --stdin)",
    )
    parser.add_argument(
        "--height", type=int, metavar="H",
        help="Frame height in pixels (required with --stdin)",
    )
    parser.add_argument(
        "--max-frames", type=int, metavar="N",
        help="Process at most N frames then stop",
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    passphrase = args.passphrase or os.environ.get("GPG_PASSPHRASE")

    if args.stdin:
        if not args.width or not args.height:
            print("Error: --width and --height are required with --stdin", file=sys.stderr)
            sys.exit(1)
        width, height = args.width, args.height
        frame_iter = frames_from_stdin(width, height)
        output_path = args.output or "stream.fpchain"
    else:
        if not Path(args.input).exists():
            print(f"Error: input file not found: {args.input}", file=sys.stderr)
            sys.exit(1)
        width, height, fps = get_video_info(args.input)
        if args.verbose:
            print(f"Video: {width}x{height} @ {fps:.3f} fps")
        frame_iter = extract_frames(args.input, width, height, max_frames=args.max_frames)
        output_path = args.output or (Path(args.input).stem + ".fpchain")

    print(f"Fingerprinting to : {output_path}")
    print(f"Signing with key  : {args.key}")

    frame_count = 0
    with ChainWriter(
        output_path=output_path,
        gpg_key_fingerprint=args.key,
        width=width,
        height=height,
        passphrase=passphrase,
        gpg_home=args.gpg_home,
    ) as writer:
        for frame_bytes in frame_iter:
            ts = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
            writer.add_frame(frame_bytes, timestamp=ts)
            frame_count += 1
            if args.verbose or frame_count % 100 == 0:
                print(f"\r  Processed frame {frame_count}...", end="", flush=True)

    print(f"\nDone. Fingerprinted {frame_count} frame(s).")
    print(f"Chain written to  : {output_path}")


if __name__ == "__main__":
    main()
