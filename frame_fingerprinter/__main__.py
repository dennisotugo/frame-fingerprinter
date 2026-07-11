"""Allow ``python -m frame_fingerprinter --help`` as an entry point."""

import argparse
import sys


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m frame_fingerprinter",
        description="frame-fingerprinter – cryptographic per-frame video verification",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Commands:\n"
            "  fingerprint-video   Sign every frame of a video file\n"
            "  verify-video        Verify a .fpchain sidecar file\n"
            "\n"
            "Examples:\n"
            "  fingerprint-video -i dashcam.mp4 -k YOUR_KEY_FP\n"
            "  verify-video -c dashcam.fpchain -v dashcam.mp4\n"
            "\n"
            "Run 'fingerprint-video --help' or 'verify-video --help' for full options.\n"
        ),
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__import__('frame_fingerprinter').__version__}",
    )
    # Show help by default (no sub-commands handled here; each tool has its own main)
    parser.parse_args()
    parser.print_help()
    sys.exit(0)


if __name__ == "__main__":
    main()
