"""
Frame fingerprint chain management.

The ``.fpchain`` file format is **JSON Lines**: every line is a JSON object.
The first line is a *header* record (``"type": "fpchain_header"``); every
subsequent line is a *fingerprint* record produced by :func:`build_fingerprint`
with an additional ``"signature"`` field.

This module provides:

- :class:`ChainWriter` – context manager that accepts raw frames one at a time
  and writes signed fingerprint records to a ``.fpchain`` file.
- :func:`load_chain` – parse a ``.fpchain`` file and return the header and
  list of fingerprint records.
- :class:`ChainVerifier` – verify the integrity of a ``.fpchain`` file,
  optionally cross-checking each frame's hash against actual video frames.
"""

import json
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import IO, Iterator, Optional

from .fingerprint import (
    GENESIS_HASH,
    build_fingerprint,
    compute_chain_hash,
    compute_frame_hash,
    extract_frame_properties,
)
from .signer import sign_chain_hash, verify_signature

__all__ = [
    "ChainWriter",
    "ChainVerifier",
    "load_chain",
    "FPCHAIN_VERSION",
]

FPCHAIN_VERSION = 1


def _now_utc() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


class ChainWriter:
    """
    Build and write a frame fingerprint chain to a ``.fpchain`` file.

    Each call to :meth:`add_frame` queues a frame.  Because frame *N*'s
    fingerprint must include properties of frame *N+1*, the fingerprint is
    not finalised until the next frame arrives (or the context manager exits).

    Usage::

        with ChainWriter("output.fpchain", key_id, width, height) as writer:
            for frame_bytes in frame_source:
                writer.add_frame(frame_bytes)

    Args:
        output_path:         Path where the ``.fpchain`` file is written.
        gpg_key_fingerprint: Fingerprint or key ID used for signing.
        width:               Frame width in pixels.
        height:              Frame height in pixels.
        passphrase:          GPG key passphrase (``None`` if none).
        gpg_home:            Custom GPG home directory (``None`` for default).
    """

    def __init__(
        self,
        output_path: str,
        gpg_key_fingerprint: str,
        width: int,
        height: int,
        passphrase: Optional[str] = None,
        gpg_home: Optional[str] = None,
    ):
        self.output_path = Path(output_path)
        self.gpg_key_fingerprint = gpg_key_fingerprint
        self.width = width
        self.height = height
        self.passphrase = passphrase
        self.gpg_home = gpg_home

        self._frame_number = 0
        self._prev_chain_hash = GENESIS_HASH
        self._pending: Optional[tuple[bytes, str]] = None  # (frame_bytes, timestamp)
        self._file: Optional[IO[str]] = None

    def __enter__(self) -> "ChainWriter":
        self._file = open(self.output_path, "w", encoding="utf-8")
        header = {
            "type": "fpchain_header",
            "version": FPCHAIN_VERSION,
            "width": self.width,
            "height": self.height,
            "gpg_key_fingerprint": self.gpg_key_fingerprint,
            "created_at": _now_utc(),
        }
        self._file.write(json.dumps(header) + "\n")
        self._file.flush()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        try:
            if exc_type is None and self._pending is not None:
                # Normal exit: flush the last pending frame (no next frame).
                frame_bytes, timestamp = self._pending
                self._write_fingerprint(frame_bytes, timestamp, next_frame_bytes=None)
                self._pending = None
        finally:
            if self._file is not None:
                self._file.close()
                self._file = None
        # Return False so that any exception is propagated to the caller.
        return False

    def add_frame(self, frame_bytes: bytes, timestamp: Optional[str] = None) -> None:
        """
        Add a raw RGB24 frame to the chain.

        Call this method once per frame, in display order.  The timestamp
        defaults to the current UTC time if not provided.
        """
        if timestamp is None:
            timestamp = _now_utc()

        if self._pending is not None:
            prev_bytes, prev_ts = self._pending
            self._write_fingerprint(prev_bytes, prev_ts, next_frame_bytes=frame_bytes)

        self._pending = (frame_bytes, timestamp)

    def _write_fingerprint(
        self,
        frame_bytes: bytes,
        timestamp: str,
        next_frame_bytes: Optional[bytes],
    ) -> None:
        assert self._file is not None, "ChainWriter must be used as a context manager"
        fp = build_fingerprint(
            frame_number=self._frame_number,
            timestamp=timestamp,
            width=self.width,
            height=self.height,
            frame_bytes=frame_bytes,
            prev_chain_hash=self._prev_chain_hash,
            next_frame_bytes=next_frame_bytes,
        )
        signature = sign_chain_hash(
            fp["chain_hash"],
            key_fingerprint=self.gpg_key_fingerprint,
            passphrase=self.passphrase,
            gpg_home=self.gpg_home,
        )
        fp["signature"] = signature

        self._file.write(json.dumps(fp) + "\n")
        self._file.flush()

        self._prev_chain_hash = fp["chain_hash"]
        self._frame_number += 1


def load_chain(chain_path: str) -> tuple[dict, list[dict]]:
    """
    Load a ``.fpchain`` file.

    Args:
        chain_path: Path to the ``.fpchain`` file.

    Returns:
        A ``(header, records)`` tuple where *header* is the header dict and
        *records* is a list of fingerprint dicts.

    Raises:
        :exc:`ValueError` if no header line is found.
    """
    records: list[dict] = []
    header: Optional[dict] = None
    with open(chain_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            if record.get("type") == "fpchain_header":
                header = record
            else:
                records.append(record)

    if header is None:
        raise ValueError(f"No fpchain_header found in '{chain_path}'")
    return header, records


def _lookahead_pairs(
    it: Iterator[bytes],
) -> Iterator[tuple[bytes, Optional[bytes]]]:
    """
    Yield ``(current, next_or_None)`` pairs from *it*.

    Holds at most two frames in memory at any given time, keeping verification
    memory-efficient regardless of video length.
    """
    buf: deque[bytes] = deque(maxlen=2)
    # Pre-fill up to two frames.
    for _ in range(2):
        try:
            buf.append(next(it))
        except StopIteration:
            break
    while buf:
        current = buf[0]
        nxt: Optional[bytes] = buf[1] if len(buf) > 1 else None
        yield current, nxt
        buf.popleft()
        # Refill the look-ahead slot.
        if nxt is not None:
            try:
                buf.append(next(it))
            except StopIteration:
                pass


class ChainVerifier:
    """
    Verify the integrity of a ``.fpchain`` file.

    Optionally cross-checks each frame's hash against actual video frame data
    supplied as a byte iterator.  Verification is **streaming**: only two raw
    frames are held in memory at any time, making it safe to use against
    arbitrarily large recordings.

    Args:
        gpg_home: Custom GPG home directory (``None`` for default ``~/.gnupg``).
    """

    def __init__(self, gpg_home: Optional[str] = None):
        self.gpg_home = gpg_home

    def verify_chain_file(
        self,
        chain_path: str,
        frame_iter: Optional[Iterator[bytes]] = None,
        verbose: bool = False,
    ) -> dict:
        """
        Verify the integrity of a ``.fpchain`` file.

        Checks performed for every fingerprint record:

        1. **Chain continuity** – ``prev_chain_hash`` matches the ``chain_hash``
           of the previous record (or :data:`GENESIS_HASH` for the first).
        2. **Chain hash recomputation** – the stored ``chain_hash`` is
           reproduced from the other record fields.
        3. **GPG signature** – the ``signature`` field is a valid detached
           signature over the ``chain_hash``.
        4. *(optional)* **Frame hash** – if *frame_iter* is given, the
           ``frame_hash`` is reproduced from the actual video frame bytes.
        5. *(optional)* **Next-frame properties** – if *frame_iter* is given,
           the ``next_frame_properties`` recorded in frame *N* match the
           properties extracted from the actual frame *N+1*.

        Args:
            chain_path:  Path to the ``.fpchain`` file.
            frame_iter:  Iterator yielding raw RGB24 frame bytes in display
                         order.  When provided, checks 4 and 5 are also run.
                         Only two frames are held in memory at a time.
            verbose:     Print per-frame status to stdout.

        Returns:
            Dict with:

            - ``valid``        – :class:`bool`, ``True`` iff no errors were found.
            - ``total_frames`` – number of fingerprint records examined.
            - ``header``       – the parsed header dict.
            - ``errors``       – list of human-readable error strings.
        """
        header, records = load_chain(chain_path)
        errors: list[str] = []
        prev_chain_hash = GENESIS_HASH
        total = len(records)

        # Build a streaming look-ahead iterator when frame data is supplied.
        # This avoids loading the entire video into RAM.
        frame_pairs: Optional[Iterator[tuple[bytes, Optional[bytes]]]] = None
        if frame_iter is not None:
            frame_pairs = _lookahead_pairs(frame_iter)

        for i, record in enumerate(records):
            frame_num = record.get("frame_number", i)
            prefix = f"Frame {frame_num}"

            # 1. Chain continuity
            stored_prev = record.get("prev_chain_hash")
            if stored_prev != prev_chain_hash:
                errors.append(
                    f"{prefix}: prev_chain_hash mismatch "
                    f"(expected {prev_chain_hash!r}, got {stored_prev!r})"
                )

            # 2. Recompute chain_hash
            recomputed = compute_chain_hash(
                frame_number=record["frame_number"],
                timestamp=record["timestamp"],
                width=record["width"],
                height=record["height"],
                frame_hash=record["frame_hash"],
                prev_chain_hash=record["prev_chain_hash"],
                next_frame_properties=record.get("next_frame_properties"),
            )
            if recomputed != record["chain_hash"]:
                errors.append(f"{prefix}: chain_hash recomputation mismatch")

            # 3. GPG signature
            sig_result = verify_signature(
                record["chain_hash"],
                record.get("signature", ""),
                gpg_home=self.gpg_home,
            )
            if not sig_result["valid"]:
                errors.append(
                    f"{prefix}: invalid GPG signature "
                    f"(status: {sig_result.get('status')})"
                )
            elif verbose:
                print(f"  {prefix}: signature OK (key: {sig_result.get('key_id')})")

            # 4 & 5. Cross-check against actual video frames (streaming)
            if frame_pairs is not None:
                pair = next(frame_pairs, None)
                if pair is None:
                    errors.append(f"{prefix}: no video frame available for verification")
                else:
                    actual_frame, next_frame = pair
                    width = record["width"]
                    height = record["height"]

                    actual_hash = compute_frame_hash(actual_frame)
                    if actual_hash != record["frame_hash"]:
                        errors.append(f"{prefix}: frame_hash mismatch with video data")

                    stored_next = record.get("next_frame_properties")
                    if stored_next is not None:
                        if next_frame is not None:
                            expected_props = extract_frame_properties(
                                next_frame, width, height
                            )
                            if expected_props != stored_next:
                                errors.append(
                                    f"{prefix}: next_frame_properties mismatch "
                                    "with video data"
                                )
                        else:
                            errors.append(
                                f"{prefix}: next_frame_properties present but "
                                "no next frame in video"
                            )
                    elif i < total - 1:
                        errors.append(
                            f"{prefix}: next_frame_properties is None but "
                            "not the last frame"
                        )

            prev_chain_hash = record["chain_hash"]

        return {
            "valid": len(errors) == 0,
            "total_frames": total,
            "header": header,
            "errors": errors,
        }
