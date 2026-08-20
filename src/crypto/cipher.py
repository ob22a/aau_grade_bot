"""AES-256-GCM encryption service for sensitive portal data."""

from __future__ import annotations

import base64
import secrets
from dataclasses import dataclass

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


@dataclass(frozen=True)
class Ciphertext:
    """Binary-safe representation of AES-GCM output."""

    nonce: bytes
    ciphertext: bytes

    def to_token(self) -> str:
        """Serialize ciphertext to a URL-safe string for database storage."""
        payload = self.nonce + self.ciphertext
        return base64.urlsafe_b64encode(payload).decode("ascii")

    @classmethod
    def from_token(cls, token: str, nonce_size: int = 12) -> "Ciphertext":
        """Deserialize ciphertext from a URL-safe storage token."""
        payload = base64.urlsafe_b64decode(token.encode("ascii"))
        if len(payload) < nonce_size:
            raise ValueError("Ciphertext token is too short")
        return cls(nonce=payload[:nonce_size], ciphertext=payload[nonce_size:])


class AesGcmCipher:
    """AES-256-GCM cipher with fresh nonces and authenticated decryption."""

    NONCE_SIZE = 12
    KEY_SIZE = 32

    def __init__(self, key: bytes) -> None:
        if len(key) != self.KEY_SIZE:
            raise ValueError("AES-256-GCM requires a 32-byte key")
        self._aesgcm = AESGCM(key)

    @classmethod
    def from_base64_key(cls, encoded_key: str) -> "AesGcmCipher":
        """Create a cipher from a base64-encoded 32-byte key."""
        key = base64.urlsafe_b64decode(encoded_key.encode("ascii"))
        return cls(key)

    @staticmethod
    def generate_key() -> str:
        """Generate a fresh base64-encoded 32-byte key."""
        return base64.urlsafe_b64encode(secrets.token_bytes(AesGcmCipher.KEY_SIZE)).decode("ascii")

    def encrypt(self, plaintext: str, associated_data: bytes | None = None) -> str:
        """Encrypt plaintext and return a URL-safe token."""
        nonce = secrets.token_bytes(self.NONCE_SIZE)
        ciphertext = self._aesgcm.encrypt(
            nonce,
            plaintext.encode("utf-8"),
            associated_data,
        )
        return Ciphertext(nonce=nonce, ciphertext=ciphertext).to_token()

    def decrypt(self, token: str, associated_data: bytes | None = None) -> str:
        """Decrypt a URL-safe token into plaintext."""
        payload = Ciphertext.from_token(token, nonce_size=self.NONCE_SIZE)
        try:
            plaintext = self._aesgcm.decrypt(
                payload.nonce,
                payload.ciphertext,
                associated_data,
            )
        except InvalidTag as exc:
            raise ValueError("Ciphertext authentication failed") from exc
        return plaintext.decode("utf-8")
