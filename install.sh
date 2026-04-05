#!/usr/bin/env bash
# install.sh – One-script installer for frame-fingerprinter.
#
# Installs system dependencies (ffmpeg, gpg) and the Python package.
# Supports Debian/Ubuntu, Fedora/RHEL/CentOS, macOS (Homebrew), and Windows
# (via WSL or Conda).
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/dennisotugo/frame-fingerprinter/main/install.sh | bash
#   # or
#   bash install.sh [--dev]
#
# Flags:
#   --dev   Also install development dependencies (pytest, Pillow)

set -euo pipefail

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
info()    { echo -e "${GREEN}[INFO]${NC} $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC} $*"; }
die()     { echo -e "${RED}[ERROR]${NC} $*" >&2; exit 1; }

DEV_MODE=false
for arg in "$@"; do [[ "$arg" == "--dev" ]] && DEV_MODE=true; done

# ---------------------------------------------------------------------------
# Detect OS and install system packages
# ---------------------------------------------------------------------------

SYSTEM_DEPS_OK=true

install_system_deps() {
    if command -v apt-get &>/dev/null; then
        info "Detected Debian/Ubuntu – installing ffmpeg and gnupg"
        sudo apt-get update -qq
        sudo apt-get install -y ffmpeg gnupg
    elif command -v dnf &>/dev/null; then
        info "Detected Fedora/RHEL – installing ffmpeg and gnupg"
        sudo dnf install -y ffmpeg gnupg2
    elif command -v yum &>/dev/null; then
        info "Detected CentOS/RHEL – installing ffmpeg and gnupg"
        sudo yum install -y ffmpeg gnupg2
    elif command -v brew &>/dev/null; then
        info "Detected macOS/Homebrew – installing ffmpeg and gnupg"
        brew install ffmpeg gnupg
    else
        warn "Package manager not recognised."
        warn "Please install 'ffmpeg' and 'gpg' manually before continuing."
        SYSTEM_DEPS_OK=false
    fi
}

check_cmd() {
    if ! command -v "$1" &>/dev/null; then
        return 1
    fi
    return 0
}

if ! check_cmd ffmpeg || ! check_cmd gpg; then
    install_system_deps
fi

check_cmd ffmpeg || die "ffmpeg not found after installation attempt."
check_cmd gpg    || die "gpg not found after installation attempt."

# ---------------------------------------------------------------------------
# Detect Python
# ---------------------------------------------------------------------------

PYTHON=""
for py in python3 python; do
    if command -v "$py" &>/dev/null; then
        ver=$("$py" -c 'import sys; print(sys.version_info >= (3, 10))')
        if [[ "$ver" == "True" ]]; then
            PYTHON="$py"
            break
        fi
    fi
done

[[ -z "$PYTHON" ]] && die "Python 3.10+ is required. Please install it and re-run."
info "Using Python: $PYTHON ($($PYTHON --version))"

# ---------------------------------------------------------------------------
# Install Python package
# ---------------------------------------------------------------------------

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ "$DEV_MODE" == "true" ]]; then
    info "Installing package with dev dependencies…"
    "$PYTHON" -m pip install --upgrade pip
    "$PYTHON" -m pip install -e "$SCRIPT_DIR[dev]"
else
    info "Installing package…"
    "$PYTHON" -m pip install --upgrade pip
    "$PYTHON" -m pip install "$SCRIPT_DIR"
fi

# ---------------------------------------------------------------------------
# Verify installation
# ---------------------------------------------------------------------------

info "Verifying installation…"
"$PYTHON" -c "import frame_fingerprinter; print('frame_fingerprinter', frame_fingerprinter.__version__)" \
    || die "Python package import failed."

command -v fingerprint-video &>/dev/null \
    && info "CLI: fingerprint-video is available" \
    || warn "fingerprint-video CLI not found in PATH – you may need to add pip's bin dir to PATH."

command -v verify-video &>/dev/null \
    && info "CLI: verify-video is available" \
    || warn "verify-video CLI not found in PATH."

echo
echo -e "${GREEN}✓ frame-fingerprinter installed successfully!${NC}"
echo
echo "Quick start:"
echo "  1. Generate a GPG signing key (if you don't have one):"
echo "       gpg --full-generate-key"
echo "  2. List keys and note the 40-char fingerprint:"
echo "       gpg --list-secret-keys --keyid-format LONG"
echo "  3. Fingerprint a video:"
echo "       fingerprint-video -i dashcam.mp4 -k <YOUR_KEY_FINGERPRINT>"
echo "  4. Verify the fingerprint chain:"
echo "       verify-video -c dashcam.fpchain -v dashcam.mp4"
echo
echo "For more usage examples, see README.md"
