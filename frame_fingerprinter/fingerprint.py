"""
Core frame fingerprinting logic.

Each frame's fingerprint is a JSON object containing:

- ``frame_number``         – sequential 0-based frame index
- ``timestamp``            – ISO-8601 UTC datetime of capture
- ``width`` / ``height``   – frame dimensions in pixels
- ``frame_hash``           – SHA-256 of the raw RGB24 frame bytes
- ``prev_chain_hash``      – SHA-256 of the *previous* frame's fingerprint payload,
                             forming a forward-only hash chain (GENESIS_HASH for frame 0)
- ``next_frame_properties``– lightweight perceptual properties sampled from the *next*
                             frame, creating a bidirectional cross-frame binding that
                             prevents silent frame substitution (``None`` for the last frame)
- ``chain_hash``           – SHA-256 of the canonical JSON of all fields above; this is
                             the value that gets GPG-signed
"""

import hashlib
import json
from typing import Optional

import numpy as np

__all__ = [
    "GENESIS_HASH",
    "SAMPLE_GRID",
    "compute_frame_hash",
    "extract_frame_properties",
    "compute_chain_hash",
    "build_fingerprint",
]

# Sentinel hash used as ``prev_chain_hash`` for the very first frame.
GENESIS_HASH = "sha256:" + "0" * 64

# Grid dimension used when sampling the next frame for binding properties.
# A SAMPLE_GRID x SAMPLE_GRID lattice of pixels is extracted (16 by default).
SAMPLE_GRID = 4

# Pre-compute sample-point row/column indices so they are not recomputed
# on every frame.  Updated lazily when SAMPLE_GRID changes (not expected in
# normal usage, but makes the code correct if someone patches SAMPLE_GRID).
_sample_rows: Optional[np.ndarray] = None
_sample_cols: Optional[np.ndarray] = None
_sample_grid_cached: int = 0


def _get_sample_indices(height: int, width: int) -> tuple[np.ndarray, np.ndarray]:
    """Return (row_indices, col_indices) for the SAMPLE_GRID lattice."""
    global _sample_rows, _sample_cols, _sample_grid_cached
    if _sample_grid_cached != SAMPLE_GRID:
        g = SAMPLE_GRID
        frac = np.arange(g) + 0.5
        _sample_rows = (frac / g * height).astype(int)
        _sample_cols = (frac / g * width).astype(int)
        _sample_grid_cached = g
    # Scale to current frame dimensions each call (cheap)
    g = SAMPLE_GRID
    frac = np.arange(g) + 0.5
    rows = (frac / g * height).astype(int)
    cols = (frac / g * width).astype(int)
    return rows, cols


def compute_frame_hash(frame_bytes: bytes) -> str:
    """Return ``sha256:<hex>`` of the raw frame bytes."""
    return "sha256:" + hashlib.sha256(frame_bytes).hexdigest()


def extract_frame_properties(frame_bytes: bytes, width: int, height: int) -> dict:
    """
    Extract lightweight qualifying properties from a frame.

    The properties are intentionally *lightweight* – they are **not** a full
    hash of the frame.  Their purpose is to bind frame N's fingerprint to a
    few measurable characteristics of frame N+1 so that silently swapping
    frame N+1 with a synthesised frame would invalidate frame N's signature.

    Returns a dict with:

    - ``mean_r``, ``mean_g``, ``mean_b`` – per-channel pixel mean (0-255 range)
    - ``std_r``, ``std_g``, ``std_b``   – per-channel pixel standard deviation
    - ``sample_pixels``                  – list of [R, G, B] pixel values sampled
                                           at a uniform ``SAMPLE_GRID × SAMPLE_GRID``
                                           lattice across the frame
    """
    arr = np.frombuffer(frame_bytes, dtype=np.uint8).reshape(height, width, 3)

    means = arr.mean(axis=(0, 1))
    stds = arr.std(axis=(0, 1))

    # Vectorised pixel sampling: build index grids and gather in one shot
    # instead of a Python-level nested loop.
    rows, cols = _get_sample_indices(height, width)
    # rows/cols are 1-D; mesh them to get all (row, col) pairs
    row_idx, col_idx = np.meshgrid(rows, cols, indexing="ij")
    sampled = arr[row_idx.ravel(), col_idx.ravel()]  # shape (SAMPLE_GRID**2, 3)
    sample_pixels = sampled.tolist()

    return {
        "mean_r": round(float(means[0]), 4),
        "mean_g": round(float(means[1]), 4),
        "mean_b": round(float(means[2]), 4),
        "std_r": round(float(stds[0]), 4),
        "std_g": round(float(stds[1]), 4),
        "std_b": round(float(stds[2]), 4),
        "sample_pixels": sample_pixels,
    }


def compute_chain_hash(
    frame_number: int,
    timestamp: str,
    width: int,
    height: int,
    frame_hash: str,
    prev_chain_hash: str,
    next_frame_properties: Optional[dict],
) -> str:
    """
    Compute the ``chain_hash`` – a SHA-256 over all fingerprint fields.

    The canonical serialisation uses ``json.dumps`` with ``sort_keys=True`` and
    no extra whitespace so that the output is byte-for-byte identical across
    implementations and platforms.

    This hash is the value that is passed to GPG for signing.
    """
    payload = {
        "frame_number": frame_number,
        "timestamp": timestamp,
        "width": width,
        "height": height,
        "frame_hash": frame_hash,
        "prev_chain_hash": prev_chain_hash,
        "next_frame_properties": next_frame_properties,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_fingerprint(
    frame_number: int,
    timestamp: str,
    width: int,
    height: int,
    frame_bytes: bytes,
    prev_chain_hash: str,
    next_frame_bytes: Optional[bytes],
) -> dict:
    """
    Build a complete (unsigned) fingerprint record for a single frame.

    Args:
        frame_number:     0-based sequential frame index.
        timestamp:        ISO-8601 UTC datetime string for this frame.
        width:            Frame width in pixels.
        height:           Frame height in pixels.
        frame_bytes:      Raw RGB24 bytes for this frame.
        prev_chain_hash:  ``chain_hash`` of the previous frame fingerprint,
                          or :data:`GENESIS_HASH` for the very first frame.
        next_frame_bytes: Raw RGB24 bytes of the *next* frame, or ``None``
                          if this is the last frame in the stream.

    Returns:
        Fingerprint dict **without** a ``signature`` field.  Add the GPG
        signature under the key ``"signature"`` before persisting.
    """
    frame_hash = compute_frame_hash(frame_bytes)

    next_props = None
    if next_frame_bytes is not None:
        next_props = extract_frame_properties(next_frame_bytes, width, height)

    chain_hash = compute_chain_hash(
        frame_number,
        timestamp,
        width,
        height,
        frame_hash,
        prev_chain_hash,
        next_props,
    )

    return {
        "frame_number": frame_number,
        "timestamp": timestamp,
        "width": width,
        "height": height,
        "frame_hash": frame_hash,
        "prev_chain_hash": prev_chain_hash,
        "next_frame_properties": next_props,
        "chain_hash": chain_hash,
    }
