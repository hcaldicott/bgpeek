"""Fernet encryption for stored passwords (SSH credentials)."""

from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken

from bgpeek.config import settings


def _get_fernet() -> Fernet | None:
    """Return a Fernet instance if encryption key is configured, else None."""
    if not settings.encryption_key:
        return None
    return Fernet(settings.encryption_key.encode())


def encrypt_password(plaintext: str) -> str:
    """Encrypt a password. Returns the ciphertext as a string.

    If no encryption key is configured, stores as-is (for dev/testing).
    """
    f = _get_fernet()
    if f is None:
        return plaintext
    return f.encrypt(plaintext.encode()).decode()


def decrypt_password(ciphertext: str) -> str:
    """Decrypt a stored password. Returns plaintext.

    If no encryption key is configured, returns as-is.
    Raises ValueError if decryption fails (wrong key or corrupted data).
    """
    f = _get_fernet()
    if f is None:
        return ciphertext
    try:
        return f.decrypt(ciphertext.encode()).decode()
    except InvalidToken as exc:
        raise ValueError("Failed to decrypt password — wrong BGPEEK_ENCRYPTION_KEY?") from exc
