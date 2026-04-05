"""Tests for GPG signing and verification (signer.py)."""

import os
import tempfile

import pytest

from frame_fingerprinter.signer import generate_test_key, sign_chain_hash, verify_signature


# ---------------------------------------------------------------------------
# Module-scoped GPG environment (one key pair reused across all tests)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def gpg_env():
    """Create a temporary GPG home directory with a single test key pair."""
    with tempfile.TemporaryDirectory(prefix="fptest_gpg_") as gpg_home:
        os.chmod(gpg_home, 0o700)
        key_fp = generate_test_key(
            name="Test Signer",
            email="test@example.com",
            passphrase="testpass",
            gpg_home=gpg_home,
        )
        yield {
            "gpg_home": gpg_home,
            "key_fingerprint": key_fp,
            "passphrase": "testpass",
        }


# ---------------------------------------------------------------------------
# sign_chain_hash
# ---------------------------------------------------------------------------

class TestSignChainHash:
    def test_returns_string(self, gpg_env):
        sig = sign_chain_hash(
            "sha256:" + "a" * 64,
            gpg_env["key_fingerprint"],
            passphrase=gpg_env["passphrase"],
            gpg_home=gpg_env["gpg_home"],
        )
        assert isinstance(sig, str)

    def test_contains_pgp_header(self, gpg_env):
        sig = sign_chain_hash(
            "sha256:" + "a" * 64,
            gpg_env["key_fingerprint"],
            passphrase=gpg_env["passphrase"],
            gpg_home=gpg_env["gpg_home"],
        )
        assert "BEGIN PGP SIGNATURE" in sig

    def test_different_data_different_signature(self, gpg_env):
        def _sign(data):
            return sign_chain_hash(
                data,
                gpg_env["key_fingerprint"],
                passphrase=gpg_env["passphrase"],
                gpg_home=gpg_env["gpg_home"],
            )
        assert _sign("sha256:" + "a" * 64) != _sign("sha256:" + "b" * 64)


# ---------------------------------------------------------------------------
# verify_signature
# ---------------------------------------------------------------------------

class TestVerifySignature:
    def _sign(self, gpg_env, data):
        return sign_chain_hash(
            data,
            gpg_env["key_fingerprint"],
            passphrase=gpg_env["passphrase"],
            gpg_home=gpg_env["gpg_home"],
        )

    def test_valid_signature(self, gpg_env):
        data = "sha256:" + "c" * 64
        sig = self._sign(gpg_env, data)
        result = verify_signature(data, sig, gpg_home=gpg_env["gpg_home"])
        assert result["valid"] is True

    def test_wrong_data_invalid(self, gpg_env):
        data = "sha256:" + "d" * 64
        sig = self._sign(gpg_env, data)
        result = verify_signature(
            "sha256:" + "e" * 64,   # different data
            sig,
            gpg_home=gpg_env["gpg_home"],
        )
        assert result["valid"] is False

    def test_tampered_signature_invalid(self, gpg_env):
        data = "sha256:" + "f" * 64
        sig = self._sign(gpg_env, data)
        # Flip every 'A' to 'B' to tamper with the signature body
        tampered = sig.replace("A", "B")
        result = verify_signature(data, tampered, gpg_home=gpg_env["gpg_home"])
        assert result["valid"] is False

    def test_empty_signature_invalid(self, gpg_env):
        result = verify_signature(
            "sha256:" + "a" * 64,
            "",
            gpg_home=gpg_env["gpg_home"],
        )
        assert result["valid"] is False

    def test_result_has_expected_keys(self, gpg_env):
        data = "sha256:" + "1" * 64
        sig = self._sign(gpg_env, data)
        result = verify_signature(data, sig, gpg_home=gpg_env["gpg_home"])
        assert set(result) >= {"valid", "key_id", "fingerprint", "timestamp", "username", "status"}

    def test_valid_result_has_fingerprint(self, gpg_env):
        data = "sha256:" + "2" * 64
        sig = self._sign(gpg_env, data)
        result = verify_signature(data, sig, gpg_home=gpg_env["gpg_home"])
        assert result["valid"] is True
        assert result["fingerprint"] is not None
