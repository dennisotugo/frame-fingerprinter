#!/usr/bin/env python3
"""
verify_video.py – Verify a .fpchain file and optionally cross-check against a video.

The tool loads the signed fingerprint chain and validates:
  1. The GPG signature of every frame's chain_hash.
  2. The forward hash chain (each frame's prev_chain_hash equals the previous
     frame's chain_hash).
  3. The recomputed chain_hash matches the stored value.
  4. (with --video) Each frame_hash matches actual bytes decoded from the video.
  5. (with --video) next_frame_properties recorded in frame N match the
     actual properties of frame N+1 in the video.

Exit code 0 = all checks passed.  Exit code 1 = one or more checks failed.

Usage:
    python verify_video.py -c dashcam.fpchain
    python verify_video.py -c dashcam.fpchain -v dashcam.mp4 --verbose
"""

import argparse
import sys
from pathlib import Path

from frame_fingerprinter.chain import ChainVerifier
from frame_fingerprinter.ffmpeg_pipe import extract_frames, get_video_info


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Verify a .fpchain file's chain integrity and GPG signatures, "
            "optionally cross-checking against the original video."
        )
    )
    parser.add_argument(
        "--chain", "-c",
        required=True,
        metavar="FILE",
        help="Path to the .fpchain sidecar file",
    )
    parser.add_argument(
        "--video", "-v",
        metavar="FILE",
        help=(
            "Path to the video file for frame-level verification "
            "(enables frame_hash and next_frame_properties checks)"
        ),
    )
    parser.add_argument("--gpg-home", metavar="DIR", help="GPG home directory")
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print per-frame verification status",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()

    if not Path(args.chain).exists():
        print(f"Error: chain file not found: {args.chain}", file=sys.stderr)
        sys.exit(1)

    verifier = ChainVerifier(gpg_home=args.gpg_home)

    frame_iter = None
    if args.video:
        if not Path(args.video).exists():
            print(f"Error: video file not found: {args.video}", file=sys.stderr)
            sys.exit(1)
        width, height, fps = get_video_info(args.video)
        print(f"Video info : {width}x{height} @ {fps:.3f} fps")
        frame_iter = extract_frames(args.video, width, height)

    print(f"Chain file : {args.chain}")
    if args.video:
        print(f"Video file : {args.video}")
    print()

    result = verifier.verify_chain_file(
        args.chain,
        frame_iter=frame_iter,
        verbose=args.verbose,
    )

    print(f"Total frames examined: {result['total_frames']}")

    if result["valid"]:
        print("✓  Chain is VALID – all signatures and hashes check out.")
        sys.exit(0)
    else:
        print(f"✗  Chain is INVALID – {len(result['errors'])} error(s) found:")
        for err in result["errors"]:
            print(f"   • {err}")
        sys.exit(1)


if __name__ == "__main__":
    main()
