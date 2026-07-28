"""Tests for the AES-256-GCM cipher service."""

from __future__ import annotations

import base64
import pytest

from src.crypto.cipher import AesGcmCipher, Ciphertext


def test_generate_key_produces_32_byte_key() -> None:
    encoded_key = AesGcmCipher.generate_key()
    key = base64.urlsafe_b64decode(encoded_key.encode("ascii"))

    assert len(key) == AesGcmCipher.KEY_SIZE


def test_encrypt_decrypt_round_trip() -> None:
    cipher = AesGcmCipher(base64.urlsafe_b64decode(AesGcmCipher.generate_key().encode("ascii")))

    token = cipher.encrypt("super-secret-password")
    plaintext = cipher.decrypt(token)

    assert plaintext == "super-secret-password"


def test_encrypt_produces_different_tokens_for_same_plaintext() -> None:
    cipher = AesGcmCipher(base64.urlsafe_b64decode(AesGcmCipher.generate_key().encode("ascii")))

    token_one = cipher.encrypt("same-text")
    token_two = cipher.encrypt("same-text")

    assert token_one != token_two
    assert cipher.decrypt(token_one) == "same-text"
    assert cipher.decrypt(token_two) == "same-text"


def test_encrypt_decrypt_with_associated_data() -> None:
    cipher = AesGcmCipher(base64.urlsafe_b64decode(AesGcmCipher.generate_key().encode("ascii")))

    token = cipher.encrypt("sensitive-grade-json", associated_data=b"grades")
    plaintext = cipher.decrypt(token, associated_data=b"grades")

    assert plaintext == "sensitive-grade-json"


def test_decrypt_with_wrong_associated_data_fails() -> None:
    cipher = AesGcmCipher(base64.urlsafe_b64decode(AesGcmCipher.generate_key().encode("ascii")))

    token = cipher.encrypt("sensitive-grade-json", associated_data=b"grades")

    with pytest.raises(ValueError, match="authentication failed"):
        cipher.decrypt(token, associated_data=b"credentials")


def test_ciphertext_token_round_trip() -> None:
    payload = Ciphertext(nonce=b"123456789012", ciphertext=b"cipher-bytes")
    token = payload.to_token()
    restored = Ciphertext.from_token(token)

    assert restored == payload


def test_reject_invalid_key_size() -> None:
    with pytest.raises(ValueError, match="requires a 32-byte key"):
        AesGcmCipher(b"too-short-key")
