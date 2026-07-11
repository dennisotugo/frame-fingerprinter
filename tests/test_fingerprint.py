"""Tests for frame fingerprinting core logic (fingerprint.py)."""

import hashlib

import pytest

from frame_fingerprinter.fingerprint import (
    GENESIS_HASH,
    SAMPLE_GRID,
    build_fingerprint,
    compute_chain_hash,
    compute_frame_hash,
    extract_frame_properties,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_frame(width=8, height=8, r=100, g=150, b=200) -> bytes:
    """Solid-colour RGB24 test frame."""
    return bytes([r, g, b] * width * height)


def make_gradient_frame(width=8, height=8) -> bytes:
    """Simple horizontal/vertical gradient RGB24 test frame."""
    frame = bytearray()
    for y in range(height):
        for x in range(width):
            frame.extend([
                x * (255 // max(width - 1, 1)),
                y * (255 // max(height - 1, 1)),
                128,
            ])
    return bytes(frame)


# ---------------------------------------------------------------------------
# compute_frame_hash
# ---------------------------------------------------------------------------

class TestComputeFrameHash:
    def test_returns_sha256_prefix(self):
        assert compute_frame_hash(make_frame()).startswith("sha256:")

    def test_deterministic(self):
        frame = make_frame()
        assert compute_frame_hash(frame) == compute_frame_hash(frame)

    def test_different_frames_differ(self):
        assert compute_frame_hash(make_frame(r=10)) != compute_frame_hash(make_frame(r=11))

    def test_hash_length(self):
        h = compute_frame_hash(make_frame())
        assert len(h) == 7 + 64  # "sha256:" (7) + 64 hex chars

    def test_correct_value(self):
        data = b"test"
        expected = "sha256:" + hashlib.sha256(data).hexdigest()
        assert compute_frame_hash(data) == expected


# ---------------------------------------------------------------------------
# extract_frame_properties
# ---------------------------------------------------------------------------

class TestExtractFrameProperties:
    def test_returns_expected_keys(self):
        props = extract_frame_properties(make_frame(), 8, 8)
        assert set(props) == {
            "mean_r", "mean_g", "mean_b",
            "std_r", "std_g", "std_b",
            "sample_pixels",
        }

    def test_solid_colour_zero_std(self):
        props = extract_frame_properties(make_frame(r=100, g=150, b=200), 8, 8)
        assert props["std_r"] == 0.0
        assert props["std_g"] == 0.0
        assert props["std_b"] == 0.0

    def test_solid_colour_correct_mean(self):
        props = extract_frame_properties(make_frame(r=100, g=150, b=200), 8, 8)
        assert abs(props["mean_r"] - 100.0) < 0.01
        assert abs(props["mean_g"] - 150.0) < 0.01
        assert abs(props["mean_b"] - 200.0) < 0.01

    def test_sample_pixel_count(self):
        props = extract_frame_properties(make_frame(), 8, 8)
        assert len(props["sample_pixels"]) == SAMPLE_GRID * SAMPLE_GRID

    def test_sample_pixels_are_rgb_triplets(self):
        props = extract_frame_properties(make_frame(), 8, 8)
        for pixel in props["sample_pixels"]:
            assert len(pixel) == 3
            assert all(isinstance(c, int) and 0 <= c <= 255 for c in pixel)

    def test_deterministic(self):
        frame = make_frame()
        assert extract_frame_properties(frame, 8, 8) == extract_frame_properties(frame, 8, 8)

    def test_different_frames_differ(self):
        p1 = extract_frame_properties(make_frame(r=50), 8, 8)
        p2 = extract_frame_properties(make_frame(r=200), 8, 8)
        assert p1["mean_r"] != p2["mean_r"]

    def test_gradient_frame_nonzero_std(self):
        props = extract_frame_properties(make_gradient_frame(), 8, 8)
        # A gradient must have non-zero standard deviation in at least one channel
        assert props["std_r"] > 0 or props["std_g"] > 0


# ---------------------------------------------------------------------------
# compute_chain_hash
# ---------------------------------------------------------------------------

class TestComputeChainHash:
    _ARGS = (0, "2024-01-01T00:00:00+00:00", 8, 8, "sha256:" + "a" * 64, GENESIS_HASH, None)

    def test_returns_sha256_prefix(self):
        assert compute_chain_hash(*self._ARGS).startswith("sha256:")

    def test_deterministic(self):
        assert compute_chain_hash(*self._ARGS) == compute_chain_hash(*self._ARGS)

    def test_sensitive_to_frame_number(self):
        args = list(self._ARGS)
        h1 = compute_chain_hash(*args)
        args[0] = 1
        h2 = compute_chain_hash(*args)
        assert h1 != h2

    def test_sensitive_to_timestamp(self):
        args = list(self._ARGS)
        h1 = compute_chain_hash(*args)
        args[1] = "2024-06-01T00:00:00+00:00"
        h2 = compute_chain_hash(*args)
        assert h1 != h2

    def test_sensitive_to_frame_hash(self):
        args = list(self._ARGS)
        h1 = compute_chain_hash(*args)
        args[4] = "sha256:" + "b" * 64
        h2 = compute_chain_hash(*args)
        assert h1 != h2

    def test_sensitive_to_prev_chain_hash(self):
        args = list(self._ARGS)
        h1 = compute_chain_hash(*args)
        args[5] = "sha256:" + "c" * 64
        h2 = compute_chain_hash(*args)
        assert h1 != h2

    def test_sensitive_to_next_frame_properties(self):
        args = list(self._ARGS)
        h1 = compute_chain_hash(*args)
        args[6] = {"mean_r": 128.0}
        h2 = compute_chain_hash(*args)
        assert h1 != h2


# ---------------------------------------------------------------------------
# build_fingerprint
# ---------------------------------------------------------------------------

class TestBuildFingerprint:
    def _fp(self, next_frame=None, **kwargs):
        defaults = dict(
            frame_number=0,
            timestamp="2024-01-01T00:00:00+00:00",
            width=8,
            height=8,
            frame_bytes=make_frame(),
            prev_chain_hash=GENESIS_HASH,
            next_frame_bytes=next_frame,
        )
        defaults.update(kwargs)
        return build_fingerprint(**defaults)

    def test_returns_expected_fields(self):
        fp = self._fp()
        assert set(fp) == {
            "frame_number", "timestamp", "width", "height",
            "frame_hash", "prev_chain_hash", "next_frame_properties", "chain_hash",
        }

    def test_frame_hash_correct(self):
        frame = make_frame()
        fp = self._fp(frame_bytes=frame)
        assert fp["frame_hash"] == compute_frame_hash(frame)

    def test_no_next_frame_gives_none_properties(self):
        fp = self._fp(next_frame=None)
        assert fp["next_frame_properties"] is None

    def test_next_frame_gives_properties(self):
        fp = self._fp(next_frame=make_frame(r=200))
        assert fp["next_frame_properties"] is not None

    def test_prev_chain_hash_stored(self):
        fp = self._fp()
        assert fp["prev_chain_hash"] == GENESIS_HASH

    def test_chain_hash_recomputable(self):
        fp = self._fp()
        recomputed = compute_chain_hash(
            fp["frame_number"], fp["timestamp"], fp["width"], fp["height"],
            fp["frame_hash"], fp["prev_chain_hash"], fp["next_frame_properties"],
        )
        assert recomputed == fp["chain_hash"]

    def test_chain_links_frames(self):
        frame1 = make_frame(r=100)
        frame2 = make_frame(r=150)
        fp1 = build_fingerprint(0, "ts1", 8, 8, frame1, GENESIS_HASH, frame2)
        fp2 = build_fingerprint(1, "ts2", 8, 8, frame2, fp1["chain_hash"], None)
        assert fp2["prev_chain_hash"] == fp1["chain_hash"]
