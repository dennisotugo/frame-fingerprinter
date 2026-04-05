# frame-fingerprinter

**Frame-by-frame cryptographic verifier for video recordings.**

Frame-fingerprinter signs each video frame individually using GnuPG, creating a
tamper-evident chain that makes it possible to detect:

- **Inserted or deleted frames** – breaking the forward hash chain.
- **Modified frames** – invalidating both the frame's own SHA-256 hash and its
  GPG signature.
- **AI-generated frame substitution** – each frame's fingerprint includes
  lightweight perceptual *qualifying properties* of the **next** frame,
  creating a bidirectional cross-frame binding.  Silently replacing any frame
  with a synthesised one requires forging a GPG signature, which is
  cryptographically infeasible.

Designed for **dashcams and simple recording devices**, with first-class support
for FFmpeg pipelines.

---

## How it works

Each frame's fingerprint record (one JSON line in the `.fpchain` sidecar file)
contains:

| Field | Description |
|---|---|
| `frame_number` | 0-based sequential index |
| `timestamp` | ISO-8601 UTC datetime at capture time |
| `width` / `height` | Frame dimensions |
| `frame_hash` | `sha256:…` of the raw RGB24 frame bytes |
| `prev_chain_hash` | `sha256:…` of the **previous** frame's fingerprint payload – forms a forward hash chain |
| `next_frame_properties` | Lightweight perceptual properties (channel means, std deviations, sampled pixels) extracted from the **next** frame – creates a backward binding |
| `chain_hash` | `sha256:…` of the canonical JSON of all fields above; this is the GPG-signed payload |
| `signature` | ASCII-armored detached GPG signature over `chain_hash` |

The first frame uses a well-known *genesis hash* (`sha256:0000…`) as
`prev_chain_hash`.  The last frame has `next_frame_properties = null`.

### Security properties

1. **Forward chain integrity** – modifying any frame changes its `frame_hash`,
   which changes its `chain_hash` and therefore breaks the `prev_chain_hash` of
   every subsequent frame.
2. **Backward binding** – each frame's signature covers the next frame's
   perceptual properties.  Swapping a frame requires forging the GPG signature
   of its predecessor.
3. **Temporal anchoring** – the `timestamp` field in every signed fingerprint
   records the capture time of each frame, enabling date/time verification.
4. **Cryptographic non-repudiation** – GPG signatures bind the recording to a
   specific private key; the public key can be published to allow independent
   third-party verification without any shared secrets.

---

## Installation

**Requirements**

- Python 3.10+
- GnuPG 2.x (`gpg` in `PATH`)
- FFmpeg (`ffmpeg` and `ffprobe` in `PATH`)

```bash
pip install -r requirements.txt
# or
pip install -e .
```

### Generating a signing key

```bash
# Interactive
gpg --full-generate-key

# List your keys and note the fingerprint
gpg --list-secret-keys --keyid-format LONG
# Example output:
#   sec   rsa4096/ABCDEF0123456789 2024-01-01 [SC]
#         ABCDEF0123456789ABCDEF0123456789ABCDEF01
# Use the 40-char hex string as KEY_FINGERPRINT below.
```

---

## Usage

### 1. Fingerprint an existing video file

```bash
python fingerprint_video.py -i dashcam.mp4 -k KEY_FINGERPRINT
# Produces: dashcam.fpchain
```

With a custom output path and passphrase via environment variable:

```bash
export GPG_PASSPHRASE="my_key_passphrase"
python fingerprint_video.py -i dashcam.mp4 -k KEY_FINGERPRINT -o dashcam_2024.fpchain
```

### 2. Fingerprint a live recording (FFmpeg pipeline)

```bash
# Record from a webcam/dashcam and sign frames in real-time
./scripts/record_and_sign.sh \
    -i /dev/video0 \
    -o recording.mp4 \
    -k KEY_FINGERPRINT \
    -t 3600          # duration in seconds

# Produces: recording.mp4 and recording.fpchain
```

Alternatively, pipe FFmpeg output directly:

```bash
ffmpeg -f v4l2 -i /dev/video0 -f rawvideo -pix_fmt rgb24 - | \
    python fingerprint_video.py --stdin --width 1280 --height 720 -k KEY_FINGERPRINT
```

### 3. Verify a recording

**Chain integrity + GPG signatures only** (no need for the original video):

```bash
python verify_video.py -c dashcam.fpchain
```

**Full verification** (chain + frame-by-frame hash check against the video):

```bash
python verify_video.py -c dashcam.fpchain -v dashcam.mp4
```

Or use the shell wrapper:

```bash
./scripts/verify_recording.sh -c dashcam.fpchain -v dashcam.mp4 --verbose
```

The exit code is `0` (valid) or `1` (invalid).

### 4. Share the public key for independent verification

```bash
# Export your public key
gpg --armor --export KEY_FINGERPRINT > signing_key.pub.asc

# The recipient imports it and can then verify without your private key
gpg --import signing_key.pub.asc
python verify_video.py -c dashcam.fpchain -v dashcam.mp4
```

---

## .fpchain file format

The `.fpchain` sidecar is a **JSON Lines** file (one JSON object per line).

**Line 1 – header:**

```json
{
  "type": "fpchain_header",
  "version": 1,
  "width": 1920,
  "height": 1080,
  "gpg_key_fingerprint": "ABCDEF0123456789…",
  "created_at": "2024-01-01T12:00:00.000+00:00"
}
```

**Lines 2…N – fingerprint records:**

```json
{
  "frame_number": 0,
  "timestamp": "2024-01-01T12:00:00.042+00:00",
  "width": 1920,
  "height": 1080,
  "frame_hash": "sha256:a1b2c3…",
  "prev_chain_hash": "sha256:0000000000000000000000000000000000000000000000000000000000000000",
  "next_frame_properties": {
    "mean_r": 128.3, "mean_g": 110.7, "mean_b": 95.2,
    "std_r": 40.1,   "std_g": 38.5,   "std_b": 35.9,
    "sample_pixels": [[r,g,b], …]
  },
  "chain_hash": "sha256:d4e5f6…",
  "signature": "-----BEGIN PGP SIGNATURE-----\n…\n-----END PGP SIGNATURE-----\n"
}
```

---

## Running tests

```bash
pytest tests/ -v
```

---

## Package structure

```
frame_fingerprinter/
├── __init__.py
├── fingerprint.py      # SHA-256 hashing, chain-hash computation, next-frame property extraction
├── signer.py           # GnuPG signing and verification via python-gnupg
├── chain.py            # ChainWriter (build .fpchain) and ChainVerifier (verify .fpchain)
└── ffmpeg_pipe.py      # FFmpeg frame extraction generator

fingerprint_video.py    # CLI: fingerprint a video file or raw-frame stdin stream
verify_video.py         # CLI: verify a .fpchain file

scripts/
├── record_and_sign.sh  # Record with FFmpeg and sign frames in real-time
└── verify_recording.sh # Shell wrapper for verify_video.py

tests/
├── test_fingerprint.py
├── test_signer.py
└── test_chain.py
```

---

## License

MIT