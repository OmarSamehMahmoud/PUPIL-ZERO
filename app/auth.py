"""Local account and password helpers for PUPIL ZERO."""
from __future__ import annotations

import hashlib
import hmac
import secrets

def hash_password(password: str, salt: bytes | None = None) -> tuple[str, str]:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1, dklen=64)
    return salt.hex(), digest.hex()

def verify_password(password: str, salt_hex: str, digest_hex: str) -> bool:
    try:
        _, candidate = hash_password(password, bytes.fromhex(salt_hex))
        return hmac.compare_digest(candidate, digest_hex)
    except (ValueError, TypeError):
        return False

def new_session_token() -> str:
    return secrets.token_urlsafe(36)

def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()

def new_join_code() -> str:
    return secrets.token_hex(4).upper()
