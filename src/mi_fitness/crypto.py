"""Xiaomi cloud service encryption module."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import struct
import time
from typing import Any


def _rc4_crypt(key: bytes, data: bytes, *, skip: int = 1024) -> bytes:
    """RC4 encrypt/decrypt (skipping the first N keystream bytes to avoid keystream weaknesses).

    Args:
        key: RC4 key.
        data: Data to encrypt/decrypt.
        skip: Number of initial keystream bytes to skip (default 1024).

    Returns:
        The encrypted/decrypted bytes.
    """
    s = list(range(256))
    j = 0

    # KSA (Key-Scheduling Algorithm)
    for i in range(256):
        j = (j + s[i] + key[i % len(key)]) & 0xFF
        s[i], s[j] = s[j], s[i]

    # PRGA (Pseudo-Random Generation Algorithm)
    i = 0
    j = 0

    # Skip the first `skip` bytes of keystream
    for _ in range(skip):
        i = (i + 1) & 0xFF
        j = (j + s[i]) & 0xFF
        s[i], s[j] = s[j], s[i]

    # Encrypt/decrypt
    result = bytearray(len(data))
    for idx in range(len(data)):
        i = (i + 1) & 0xFF
        j = (j + s[i]) & 0xFF
        s[i], s[j] = s[j], s[i]
        result[idx] = data[idx] ^ s[(s[i] + s[j]) & 0xFF]

    return bytes(result)


def generate_nonce() -> str:
    """Generate a request nonce.

    Format: base64(random_8_bytes + minutes_since_epoch_4bytes_BE)

    Returns:
        Base64-encoded nonce string.
    """
    random_part = os.urandom(8)
    minutes = int(time.time() / 60)
    time_part = struct.pack(">I", minutes)
    return base64.b64encode(random_part + time_part).decode()


def compute_signed_nonce(ssecurity: str, nonce: str) -> str:
    """Compute the signed nonce (used for key derivation).

    signed_nonce = base64(SHA256(b64decode(ssecurity) + b64decode(nonce)))

    Args:
        ssecurity: ssecurity obtained at login (base64-encoded).
        nonce: Request nonce.

    Returns:
        Base64-encoded signed_nonce (used as the key for both RC4 and HMAC).
    """
    hash_val = hashlib.sha256(base64.b64decode(ssecurity) + base64.b64decode(nonce)).digest()
    return base64.b64encode(hash_val).decode()


# endregion


# region Signature generation
def _sha1_b64(message: str) -> str:
    """Plain SHA1 hash → Base64 encoding.

    The app uses MessageDigest("SHA1") rather than HMAC to generate the signature.

    Args:
        message: UTF-8 string to hash.

    Returns:
        Base64-encoded SHA1 digest (28 characters).
    """
    digest = hashlib.sha1(message.encode("utf-8")).digest()
    return base64.b64encode(digest).decode()


def _build_sig_message(
    method: str,
    url_path: str,
    params: dict[str, str],
    signed_nonce: str,
) -> str:
    """Build the signature message string (z94.b format).

    Format: METHOD&/path&k1=v1&k2=v2&...&signedNonce_b64
    - method in upper case
    - path with a leading /
    - params sorted lexicographically by key (TreeMap)
    - the base64 signedNonce string is appended at the end

    Args:
        method: HTTP method.
        url_path: URL path (must include the leading /).
        params: Parameter dict (empty keys/values already excluded).
        signed_nonce: Base64-encoded signed_nonce.

    Returns:
        The signature message joined with &.
    """
    parts: list[str] = [method.upper()]
    if not url_path.startswith("/"):
        url_path = "/" + url_path
    parts.append(url_path)
    for k in sorted(params.keys()):
        parts.append(f"{k}={params[k]}")
    parts.append(signed_nonce)
    return "&".join(parts)


def _rc4_stream_encrypt_values(
    key_bytes: bytes,
    sorted_entries: list[tuple[str, str]],
) -> dict[str, str]:
    """Encrypt several values with one continuous RC4 stream.

    Mimics the app's d8k behaviour: drop 1024 bytes on construction,
    then encrypt the value of each TreeMap entry in sorted order,
    all sharing the same RC4 keystream.

    Args:
        key_bytes: RC4 key (raw bytes of signed_nonce).
        sorted_entries: List of (key, value) pairs sorted by key.

    Returns:
        A {key: base64(encrypted_value)} dict.
    """
    # Concatenate all values and run them through the RC4 stream in one pass
    all_bytes = b"".join(v.encode("utf-8") for _, v in sorted_entries)
    encrypted_all = _rc4_crypt(key_bytes, all_bytes, skip=1024)

    result: dict[str, str] = {}
    pos = 0
    for k, v in sorted_entries:
        vlen = len(v.encode("utf-8"))
        result[k] = base64.b64encode(encrypted_all[pos : pos + vlen]).decode()
        pos += vlen
    return result


# endregion


# region Data encryption/decryption
def encrypt_data(signed_nonce: str, plaintext: str) -> str:
    """Encrypt data with RC4.

    Args:
        signed_nonce: Key (base64-encoded SHA256 hash).
        plaintext: Plaintext JSON string.

    Returns:
        Base64-encoded ciphertext.
    """
    key = base64.b64decode(signed_nonce)
    encrypted = _rc4_crypt(key, plaintext.encode("utf-8"))
    return base64.b64encode(encrypted).decode()


def decrypt_data(signed_nonce: str, ciphertext_b64: str) -> str:
    """Decrypt data with RC4.

    Args:
        signed_nonce: Key (base64-encoded SHA256 hash).
        ciphertext_b64: Base64-encoded ciphertext.

    Returns:
        The decrypted plaintext string.
    """
    key = base64.b64decode(signed_nonce)
    decrypted = _rc4_crypt(key, base64.b64decode(ciphertext_b64))
    return decrypted.decode("utf-8")


# endregion


# region Wrapper: build encrypted request parameters
def build_encrypted_params(
    method: str,
    url_path: str,
    ssecurity: str,
    params: dict[str, Any] | None = None,
) -> dict[str, str]:
    """Build the full set of encrypted request parameters.

    Flow (corresponds to the app's ua4.c method):
      1. Compute signed_nonce = base64(SHA256(ssecurity + nonce))
      2. Build the raw parameter TreeMap (excluding empty keys/values)
      3. rc4_hash__ = SHA1(METHOD&/path&k=v&...&signedNonce) → base64
      4. Add rc4_hash__ to the TreeMap
      5. Encrypt all TreeMap values with one continuous RC4 stream (sorted by key, drop 1024)
      6. signature = SHA1(METHOD&/path&k=enc_v&...&signedNonce) → base64
      7. Return {encrypted parameters, signature, _nonce}

    Args:
        method: HTTP method.
        url_path: API path (e.g. /app/v1/relatives/get_relative_list).
        ssecurity: ssecurity obtained at login.
        params: Parameter dict to send (JSON-serialised, then encrypted).

    Returns:
        A parameter dict containing data, signature, rc4_hash__ and _nonce.
    """
    nonce = generate_nonce()
    snonce = compute_signed_nonce(ssecurity, nonce)
    snonce_bytes = base64.b64decode(snonce)

    # Step 1: Build the raw parameter TreeMap (excluding empty keys/values)
    raw_tree: dict[str, str] = {}
    if params:
        plaintext = json.dumps(params, separators=(",", ":"), ensure_ascii=False)
        raw_tree["data"] = plaintext

    # Step 2: Compute rc4_hash__ (from the raw parameters)
    rc4_msg = _build_sig_message(method, url_path, raw_tree, snonce)
    rc4_hash_raw = _sha1_b64(rc4_msg)

    # Step 3: Insert rc4_hash__ into the TreeMap
    raw_tree["rc4_hash__"] = rc4_hash_raw

    # Step 4: Encrypt all values with one continuous RC4 stream
    sorted_entries = sorted(raw_tree.items())
    encrypted_values = _rc4_stream_encrypt_values(snonce_bytes, sorted_entries)

    # Step 5: Build the encrypted parameter TreeMap and compute the signature
    sig_msg = _build_sig_message(method, url_path, encrypted_values, snonce)
    signature = _sha1_b64(sig_msg)

    # Step 6: Assemble the final result
    result: dict[str, str] = {}
    for k, v in encrypted_values.items():
        result[k] = v
    result["signature"] = signature
    result["_nonce"] = nonce
    return result


def decrypt_response(
    ssecurity: str,
    nonce: str,
    ciphertext_b64: str,
) -> Any:
    """Decrypt an API response.

    Args:
        ssecurity: ssecurity obtained at login.
        nonce: Nonce used in the request.
        ciphertext_b64: Base64-encoded response ciphertext.

    Returns:
        The decrypted JSON object.
    """
    snonce = compute_signed_nonce(ssecurity, nonce)
    plaintext = decrypt_data(snonce, ciphertext_b64)

    try:
        return json.loads(plaintext)
    except json.JSONDecodeError:
        # May not be JSON; return the raw string
        return plaintext


# endregion
