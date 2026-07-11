"""
Frame Fingerprinter – cryptographic per-frame verification for video.

Quick start::

    from frame_fingerprinter import ChainWriter, ChainVerifier

    # Sign a video
    with ChainWriter("recording.fpchain", key_id, width, height) as w:
        for frame in frame_source:
            w.add_frame(frame)

    # Verify
    result = ChainVerifier().verify_chain_file("recording.fpchain")
    print("Valid:", result["valid"])
"""

__version__ = "0.2.0"

from .chain import ChainVerifier, ChainWriter, load_chain
from .fingerprint import (
    GENESIS_HASH,
    SAMPLE_GRID,
    build_fingerprint,
    compute_chain_hash,
    compute_frame_hash,
    extract_frame_properties,
)
from .signer import generate_test_key, sign_chain_hash, verify_signature

__all__ = [
    # Chain management
    "ChainWriter",
    "ChainVerifier",
    "load_chain",
    # Fingerprint primitives
    "GENESIS_HASH",
    "SAMPLE_GRID",
    "build_fingerprint",
    "compute_chain_hash",
    "compute_frame_hash",
    "extract_frame_properties",
    # GPG helpers
    "sign_chain_hash",
    "verify_signature",
    "generate_test_key",
]
