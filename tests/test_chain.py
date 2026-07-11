"""Tests for chain building and verification (chain.py)."""

import json
import os
import tempfile

import pytest

from frame_fingerprinter.chain import ChainVerifier, ChainWriter, load_chain
from frame_fingerprinter.fingerprint import GENESIS_HASH
from frame_fingerprinter.signer import generate_test_key


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_frame(width=4, height=4, r=100, g=150, b=200) -> bytes:
    return bytes([r, g, b] * width * height)


@pytest.fixture(scope="module")
def gpg_env():
    with tempfile.TemporaryDirectory(prefix="fpchain_test_") as gpg_home:
        os.chmod(gpg_home, 0o700)
        key_fp = generate_test_key(
            name="Chain Test",
            email="chain@example.com",
            passphrase="chaintest",
            gpg_home=gpg_home,
        )
        yield {
            "gpg_home": gpg_home,
            "key_fingerprint": key_fp,
            "passphrase": "chaintest",
        }


def build_chain(output_path, gpg_env, frames, width=4, height=4):
    """Write a chain for *frames* and return the path."""
    with ChainWriter(
        output_path=output_path,
        gpg_key_fingerprint=gpg_env["key_fingerprint"],
        width=width,
        height=height,
        passphrase=gpg_env["passphrase"],
        gpg_home=gpg_env["gpg_home"],
    ) as writer:
        for i, frame_bytes in enumerate(frames):
            writer.add_frame(frame_bytes, timestamp=f"2024-01-01T00:00:0{i}.000+00:00")
    return output_path


# ---------------------------------------------------------------------------
# ChainWriter
# ---------------------------------------------------------------------------

class TestChainWriter:
    def test_creates_file(self, gpg_env, tmp_path):
        path = str(tmp_path / "a.fpchain")
        build_chain(path, gpg_env, [make_frame(), make_frame(r=150)])
        assert os.path.exists(path)

    def test_header_present(self, gpg_env, tmp_path):
        path = str(tmp_path / "b.fpchain")
        build_chain(path, gpg_env, [make_frame()])
        header, _ = load_chain(path)
        assert header["type"] == "fpchain_header"
        assert header["version"] == 1
        assert header["width"] == 4
        assert header["height"] == 4

    def test_correct_frame_count(self, gpg_env, tmp_path):
        path = str(tmp_path / "c.fpchain")
        build_chain(path, gpg_env, [make_frame(r=i * 20) for i in range(5)])
        _, records = load_chain(path)
        assert len(records) == 5

    def test_genesis_hash_for_first_frame(self, gpg_env, tmp_path):
        path = str(tmp_path / "d.fpchain")
        build_chain(path, gpg_env, [make_frame(), make_frame(r=150)])
        _, records = load_chain(path)
        assert records[0]["prev_chain_hash"] == GENESIS_HASH

    def test_chain_links_sequential_frames(self, gpg_env, tmp_path):
        path = str(tmp_path / "e.fpchain")
        build_chain(path, gpg_env, [make_frame(r=i * 30) for i in range(4)])
        _, records = load_chain(path)
        for i in range(1, len(records)):
            assert records[i]["prev_chain_hash"] == records[i - 1]["chain_hash"]

    def test_last_frame_has_no_next_properties(self, gpg_env, tmp_path):
        path = str(tmp_path / "f.fpchain")
        build_chain(path, gpg_env, [make_frame(), make_frame(r=150)])
        _, records = load_chain(path)
        assert records[-1]["next_frame_properties"] is None

    def test_non_last_frame_has_next_properties(self, gpg_env, tmp_path):
        path = str(tmp_path / "g.fpchain")
        build_chain(path, gpg_env, [make_frame(), make_frame(r=150)])
        _, records = load_chain(path)
        assert records[0]["next_frame_properties"] is not None

    def test_signatures_present(self, gpg_env, tmp_path):
        path = str(tmp_path / "h.fpchain")
        build_chain(path, gpg_env, [make_frame(), make_frame(r=150)])
        _, records = load_chain(path)
        for record in records:
            assert "signature" in record
            assert "BEGIN PGP SIGNATURE" in record["signature"]

    def test_single_frame_chain(self, gpg_env, tmp_path):
        path = str(tmp_path / "single.fpchain")
        build_chain(path, gpg_env, [make_frame()])
        _, records = load_chain(path)
        assert len(records) == 1
        assert records[0]["prev_chain_hash"] == GENESIS_HASH
        assert records[0]["next_frame_properties"] is None


# ---------------------------------------------------------------------------
# ChainVerifier
# ---------------------------------------------------------------------------

class TestChainVerifier:
    def test_valid_chain_passes(self, gpg_env, tmp_path):
        path = str(tmp_path / "valid.fpchain")
        frames = [make_frame(r=i * 30) for i in range(3)]
        build_chain(path, gpg_env, frames)

        verifier = ChainVerifier(gpg_home=gpg_env["gpg_home"])
        result = verifier.verify_chain_file(path)

        assert result["valid"] is True
        assert result["total_frames"] == 3
        assert result["errors"] == []

    def test_valid_chain_with_frame_data_passes(self, gpg_env, tmp_path):
        path = str(tmp_path / "valid_frames.fpchain")
        frames = [make_frame(r=i * 30) for i in range(3)]
        build_chain(path, gpg_env, frames)

        verifier = ChainVerifier(gpg_home=gpg_env["gpg_home"])
        result = verifier.verify_chain_file(path, frame_iter=iter(frames))

        assert result["valid"] is True

    def test_tampered_frame_hash_detected(self, gpg_env, tmp_path):
        path = str(tmp_path / "tamper_hash.fpchain")
        frames = [make_frame(r=i * 30) for i in range(3)]
        build_chain(path, gpg_env, frames)

        header, records = load_chain(path)
        records[1]["frame_hash"] = "sha256:" + "f" * 64  # tamper

        with open(path, "w") as f:
            f.write(json.dumps({"type": "fpchain_header", **header}) + "\n")
            for r in records:
                f.write(json.dumps(r) + "\n")

        verifier = ChainVerifier(gpg_home=gpg_env["gpg_home"])
        result = verifier.verify_chain_file(path)
        assert result["valid"] is False

    def test_broken_chain_link_detected(self, gpg_env, tmp_path):
        path = str(tmp_path / "broken_link.fpchain")
        frames = [make_frame(r=i * 30) for i in range(3)]
        build_chain(path, gpg_env, frames)

        header, records = load_chain(path)
        records[2]["prev_chain_hash"] = "sha256:" + "0" * 64  # tamper

        with open(path, "w") as f:
            f.write(json.dumps({"type": "fpchain_header", **header}) + "\n")
            for r in records:
                f.write(json.dumps(r) + "\n")

        verifier = ChainVerifier(gpg_home=gpg_env["gpg_home"])
        result = verifier.verify_chain_file(path)
        assert result["valid"] is False
        assert any("prev_chain_hash" in e for e in result["errors"])

    def test_wrong_video_frames_detected(self, gpg_env, tmp_path):
        path = str(tmp_path / "wrong_frames.fpchain")
        frames = [make_frame(r=i * 30) for i in range(3)]
        build_chain(path, gpg_env, frames)

        wrong_frames = [make_frame(r=255) for _ in range(3)]

        verifier = ChainVerifier(gpg_home=gpg_env["gpg_home"])
        result = verifier.verify_chain_file(path, frame_iter=iter(wrong_frames))

        assert result["valid"] is False
        assert any("frame_hash" in e for e in result["errors"])

    def test_result_has_header(self, gpg_env, tmp_path):
        path = str(tmp_path / "header_check.fpchain")
        build_chain(path, gpg_env, [make_frame()])

        verifier = ChainVerifier(gpg_home=gpg_env["gpg_home"])
        result = verifier.verify_chain_file(path)

        assert "header" in result
        assert result["header"]["type"] == "fpchain_header"

    def test_single_frame_valid(self, gpg_env, tmp_path):
        path = str(tmp_path / "single_valid.fpchain")
        frames = [make_frame()]
        build_chain(path, gpg_env, frames)

        verifier = ChainVerifier(gpg_home=gpg_env["gpg_home"])
        result = verifier.verify_chain_file(path, frame_iter=iter(frames))
        assert result["valid"] is True
        assert result["total_frames"] == 1
