"""
Encryption utilities for securing sensitive tokens in the database.
"""

import os
from cryptography.fernet import Fernet


def get_encryption_key() -> bytes:
    """
    Get the encryption key from environment variables.
    Generates a warning if not set and falls back to a temporary key for dev/testing.
    """
    key = os.getenv("ENCRYPTION_KEY")
    if not key:
        # For development only - this ensures the app runs but warns about security
        # In production, this must be set
        import logging
        logging.getLogger(__name__).warning(
            "ENCRYPTION_KEY not set. Using temporary key. "
            "Tokens will not persist across restarts if this changes."
        )
        return Fernet.generate_key()
    return key.encode() if isinstance(key, str) else key


def encrypt_token(token: str) -> str:
    """Encrypt a plain text token."""
    if not token:
        return ""
    f = Fernet(get_encryption_key())
    return f.encrypt(token.encode()).decode()


def decrypt_token(encrypted_token: str) -> str:
    """Decrypt an encrypted token."""
    if not encrypted_token:
        return ""
    f = Fernet(get_encryption_key())
    return f.decrypt(encrypted_token.encode()).decode()
