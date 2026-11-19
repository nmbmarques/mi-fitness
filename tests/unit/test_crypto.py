"""Tests for the encryption module (crypto.py).

Covers: RC4, nonce, signatures, encrypt/decrypt round trips.
"""

from __future__ import annotations

import base64
import json

from mi_fitness.crypto import (
    _build_sig_message,
    _rc4_crypt,
    _sha1_b64,
    build_encrypted_params,
    compute_signed_nonce,
    decrypt_data,
    decrypt_response,
    encrypt_data,
    generate_nonce,
)


class TestRC4:
    """RC4 encryption/decryption tests."""

    def test_encrypt_decrypt_roundtrip(self) -> None:
        """Decrypting after encrypting should restore the plaintext."""
        key = b"test_key_123456"
        plaintext = b"Hello, MiSDK!"
        encrypted = _rc4_crypt(key, plaintext)
        decrypted = _rc4_crypt(key, encrypted)
        assert decrypted == plaintext

    def test_different_keys_produce_different_output(self) -> None:
        """Different keys should produce different ciphertexts."""
        data = b"same data"
        enc1 = _rc4_crypt(b"key_aaa", data)
        enc2 = _rc4_crypt(b"key_bbb", data)
        assert enc1 != enc2

    def test_empty_data(self) -> None:
        """Encrypting empty data should return empty."""
        result = _rc4_crypt(b"key", b"")
        assert result == b""

    def test_skip_parameter(self) -> None:
        """skip=0 and skip=1024 should produce different results."""
        key = b"test"
        data = b"data"
        r1 = _rc4_crypt(key, data, skip=0)
        r2 = _rc4_crypt(key, data, skip=1024)
        assert r1 != r2

    def test_large_data(self) -> None:
        """Large data blocks should also round-trip correctly."""
        key = b"large_key"
        data = b"x" * 100_000
        assert _rc4_crypt(key, _rc4_crypt(key, data)) == data


class TestNonce:
    """Nonce generation tests."""

    def test_nonce_is_base64(self) -> None:
        """The nonce should be a valid base64 string."""
        nonce = generate_nonce()
        decoded = base64.b64decode(nonce)
        assert len(decoded) == 12  # 8 random + 4 time

    def test_nonce_unique(self) -> None:
        """Consecutive nonces should differ (the random part differs)."""
        nonces = {generate_nonce() for _ in range(10)}
        assert len(nonces) == 10


class TestSignedNonce:
    """compute_signed_nonce tests."""

    def test_deterministic(self, ssecurity: str) -> None:
        """The same input should produce the same result."""
        nonce = generate_nonce()
        r1 = compute_signed_nonce(ssecurity, nonce)
        r2 = compute_signed_nonce(ssecurity, nonce)
        assert r1 == r2

    def test_output_is_base64(self, ssecurity: str) -> None:
        """The output should be valid base64."""
        nonce = generate_nonce()
        snonce = compute_signed_nonce(ssecurity, nonce)
        decoded = base64.b64decode(snonce)
        assert len(decoded) == 32  # SHA256


class TestSignature:
    """Signature generation tests (plain SHA1 + Base64)."""

    def test_sha1_b64_output(self) -> None:
        """SHA1 base64 output should be 28 characters."""
        result = _sha1_b64("test message")
        decoded = base64.b64decode(result)
        assert len(decoded) == 20  # SHA1

    def test_sig_msg_format(self) -> None:
        """The signature message should be in METHOD&/path&k=v&signedNonce format."""
        msg = _build_sig_message("GET", "/test/path", {"data": "hello"}, "snonce123")
        assert msg == "GET&/test/path&data=hello&snonce123"

    def test_sig_msg_method_uppercase(self) -> None:
        """The method name should be converted to upper case."""
        msg = _build_sig_message("get", "/path", {}, "sn")
        assert msg.startswith("GET&")

    def test_sig_msg_adds_leading_slash(self) -> None:
        """A leading / should be added automatically when the path has none."""
        msg = _build_sig_message("GET", "path", {}, "sn")
        assert "&/path&" in msg

    def test_sig_msg_sorted_params(self) -> None:
        """Parameters should be sorted lexicographically by key."""
        msg = _build_sig_message("GET", "/p", {"z": "1", "a": "2"}, "sn")
        assert msg == "GET&/p&a=2&z=1&sn"


class TestEncryptDecryptData:
    """encrypt_data / decrypt_data tests."""

    def test_roundtrip(self, ssecurity: str) -> None:
        """Decrypting after encrypting should restore the original."""
        nonce = generate_nonce()
        snonce = compute_signed_nonce(ssecurity, nonce)
        plaintext = '{"key": "value", "ünïcödé": "tëst ✓"}'
        encrypted = encrypt_data(snonce, plaintext)
        decrypted = decrypt_data(snonce, encrypted)
        assert decrypted == plaintext

    def test_encrypted_is_base64(self, ssecurity: str) -> None:
        """The ciphertext should be base64-encoded."""
        nonce = generate_nonce()
        snonce = compute_signed_nonce(ssecurity, nonce)
        encrypted = encrypt_data(snonce, "test")
        base64.b64decode(encrypted)  # Passes as long as no exception is raised


class TestBuildEncryptedParams:
    """build_encrypted_params integration tests."""

    def test_has_required_keys(self, ssecurity: str) -> None:
        """The result should contain data, _nonce, signature and rc4_hash__."""
        result = build_encrypted_params(
            "GET",
            "/app/v1/relatives/get_relative_list",
            ssecurity,
            {"relative_uid": 123},
        )
        assert "data" in result
        assert "_nonce" in result
        assert "signature" in result
        assert "rc4_hash__" in result

    def test_no_params_no_data_key(self, ssecurity: str) -> None:
        """There should be no data field when there are no parameters."""
        result = build_encrypted_params(
            "GET",
            "/app/v1/relatives/get_relative_list",
            ssecurity,
        )
        assert "data" not in result
        assert "_nonce" in result

    def test_can_decrypt_own_params(self, ssecurity: str) -> None:
        """Parameters we encrypted ourselves can be decrypted."""
        params = {"test": "hello", "num": 42}
        result = build_encrypted_params("POST", "/test", ssecurity, params)
        snonce = compute_signed_nonce(ssecurity, result["_nonce"])
        decrypted = decrypt_data(snonce, result["data"])
        parsed = json.loads(decrypted)
        assert parsed == params


class TestDecryptResponse:
    """decrypt_response integration tests."""

    def test_roundtrip(self, ssecurity: str) -> None:
        """Build an encrypted response and decrypt it."""
        nonce = generate_nonce()
        snonce = compute_signed_nonce(ssecurity, nonce)
        original = {"code": 0, "result": {"data": "test"}}
        encrypted = encrypt_data(snonce, json.dumps(original))
        decrypted = decrypt_response(ssecurity, nonce, encrypted)
        assert decrypted == original

    def test_non_json_returns_string(self, ssecurity: str) -> None:
        """A non-JSON response should be returned as a string."""
        nonce = generate_nonce()
        snonce = compute_signed_nonce(ssecurity, nonce)
        encrypted = encrypt_data(snonce, "not json at all")
        result = decrypt_response(ssecurity, nonce, encrypted)
        assert result == "not json at all"
