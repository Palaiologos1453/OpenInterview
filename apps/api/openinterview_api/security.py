from __future__ import annotations

import hashlib
import hmac
import os
from uuid import uuid4


def new_api_token() -> str:
    return f"oi_{uuid4().hex}{uuid4().hex}"


def hash_token(token: str, *, salt: str | None = None) -> str:
    token_salt = salt or os.urandom(16).hex()
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        token.encode("utf-8"),
        token_salt.encode("utf-8"),
        120_000,
    ).hex()
    return f"pbkdf2_sha256${token_salt}${digest}"


def verify_token(token: str, stored_hash: str) -> bool:
    try:
        algorithm, salt, expected = stored_hash.split("$", 2)
    except ValueError:
        return False
    if algorithm != "pbkdf2_sha256":
        return False
    actual = hash_token(token, salt=salt).split("$", 2)[2]
    return hmac.compare_digest(actual, expected)


def redact_secret(value: str | None) -> str | None:
    if not value:
        return value
    if len(value) <= 8:
        return "***"
    return f"{value[:4]}...{value[-4:]}"

