#!/usr/bin/env bash
# record_and_sign.sh – Record video with FFmpeg and sign each frame in real time.
#
# The script runs FFmpeg to encode a source to a video file while simultaneously
# tee-ing raw RGB24 frames to fingerprint_video.py via a named pipe.  The result
# is a video file (e.g. recording.mp4) and a matching .fpchain sidecar file.
#
# Usage:
#   ./scripts/record_and_sign.sh -i INPUT -o OUTPUT -k GPG_KEY [OPTIONS]
#
# Arguments:
#   -i INPUT       Input source: file, /dev/video0, rtsp://..., etc.
#   -o OUTPUT      Output video file (e.g. recording.mp4)
#   -k GPG_KEY     GPG key fingerprint or key ID
#   -t DURATION    Recording duration in seconds (omit for unlimited)
#   -p PASSPHRASE  GPG key passphrase (or export GPG_PASSPHRASE env var)
#   --fps FPS      Capture / encode frame rate (default: 25)
#   --width W      Frame width  (default: 1280)
#   --height H     Frame height (default: 720)
#
# Example:
#   ./scripts/record_and_sign.sh -i /dev/video0 -o dashcam.mp4 -k ABCDEF01 -t 3600
#
# Requirements:
#   ffmpeg, python3, frame_fingerprinter package (pip install -r requirements.txt)
#   A GPG private key present in the keyring.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

usage() {
    grep '^#' "$0" | grep -v '#!/' | sed 's/^# \{0,1\}//'
    exit 1
}

INPUT=""
OUTPUT=""
GPG_KEY=""
DURATION=""
FPS=25
WIDTH=1280
HEIGHT=720

while [[ $# -gt 0 ]]; do
    case "$1" in
        -i)         INPUT="$2";     shift 2 ;;
        -o)         OUTPUT="$2";    shift 2 ;;
        -k)         GPG_KEY="$2";   shift 2 ;;
        -t)         DURATION="$2";  shift 2 ;;
        -p)         GPG_PASSPHRASE="$2"; export GPG_PASSPHRASE; shift 2 ;;
        --fps)      FPS="$2";       shift 2 ;;
        --width)    WIDTH="$2";     shift 2 ;;
        --height)   HEIGHT="$2";    shift 2 ;;
        -h|--help)  usage ;;
        *)          echo "Unknown option: $1"; usage ;;
    esac
done

[[ -z "$INPUT"   ]] && { echo "Error: -i INPUT is required";   usage; }
[[ -z "$OUTPUT"  ]] && { echo "Error: -o OUTPUT is required";  usage; }
[[ -z "$GPG_KEY" ]] && { echo "Error: -k GPG_KEY is required"; usage; }

CHAIN_FILE="${OUTPUT%.*}.fpchain"
DURATION_ARGS=()
[[ -n "$DURATION" ]] && DURATION_ARGS=(-t "$DURATION")

export GPG_PASSPHRASE="${GPG_PASSPHRASE:-}"

echo "Input  : $INPUT"
echo "Output : $OUTPUT"
echo "Chain  : $CHAIN_FILE"
echo "Key    : $GPG_KEY"
echo "Size   : ${WIDTH}x${HEIGHT} @ ${FPS}fps"
echo

# Create a temporary named pipe for tee-ing raw frames to the fingerprinter.
TMPDIR_PIPE="$(mktemp -d)"
RAW_PIPE="$TMPDIR_PIPE/rawframes.pipe"
mkfifo "$RAW_PIPE"

cleanup() {
    rm -rf "$TMPDIR_PIPE"
}
trap cleanup EXIT

# Start the fingerprinter reading raw RGB24 frames from the pipe.
python3 "$ROOT_DIR/fingerprint_video.py" \
    --stdin \
    --width "$WIDTH" \
    --height "$HEIGHT" \
    --key "$GPG_KEY" \
    --output "$CHAIN_FILE" \
    < "$RAW_PIPE" &
FINGERPRINTER_PID=$!

# Run FFmpeg:
#   - Scale to the target resolution.
#   - Split the video stream into two copies.
#   - Encode one copy to the output file with libx264/aac.
#   - Pipe the other copy as raw RGB24 to the fingerprinter via the named pipe.
ffmpeg -y \
    -i "$INPUT" \
    "${DURATION_ARGS[@]}" \
    -filter_complex "[0:v]scale=${WIDTH}:${HEIGHT},split=2[encoded][raw]" \
    -map "[encoded]" -r "$FPS" -c:v libx264 -c:a aac "$OUTPUT" \
    -map "[raw]"     -r "$FPS" -f rawvideo -pix_fmt rgb24 "$RAW_PIPE"

wait "$FINGERPRINTER_PID"

echo
echo "Recording complete."
echo "  Video : $OUTPUT"
echo "  Chain : $CHAIN_FILE"
echo
echo "To verify:"
echo "  python3 $ROOT_DIR/verify_video.py --chain $CHAIN_FILE --video $OUTPUT"
