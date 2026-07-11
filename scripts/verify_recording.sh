#!/usr/bin/env bash
# verify_recording.sh – Verify a video recording against its .fpchain sidecar.
#
# Usage:
#   ./scripts/verify_recording.sh -c recording.fpchain [-v recording.mp4] [--verbose]
#
# Arguments:
#   -c CHAIN_FILE  Path to the .fpchain sidecar file (required)
#   -v VIDEO_FILE  Path to the video file; enables full frame-level verification
#   --verbose      Print per-frame verification details
#
# Exit code 0 = chain is VALID.  Exit code 1 = chain is INVALID.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

usage() {
    grep '^#' "$0" | grep -v '#!/' | sed 's/^# \{0,1\}//'
    exit 1
}

CHAIN_FILE=""
VIDEO_FILE=""
VERBOSE=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        -c)         CHAIN_FILE="$2"; shift 2 ;;
        -v)         VIDEO_FILE="$2"; shift 2 ;;
        --verbose)  VERBOSE="--verbose"; shift ;;
        -h|--help)  usage ;;
        *)          echo "Unknown option: $1"; usage ;;
    esac
done

[[ -z "$CHAIN_FILE" ]] && { echo "Error: -c CHAIN_FILE is required"; usage; }

VIDEO_ARGS=()
[[ -n "$VIDEO_FILE" ]] && VIDEO_ARGS=(--video "$VIDEO_FILE")

exec python3 "$ROOT_DIR/verify_video.py" \
    --chain "$CHAIN_FILE" \
    "${VIDEO_ARGS[@]}" \
    $VERBOSE
