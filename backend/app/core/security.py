"""Passwords (bcrypt), access tokens (JWT) and refresh tokens (random, stored hashed)."""

import hashlib
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.core.config import settings

ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def create_access_token(user_id: uuid.UUID, role: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "role": role,
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=settings.ACCESS_TOKEN_MINUTES),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict:
    """Raises jwt.PyJWTError if the token is invalid, expired or not an access token."""
    payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[ALGORITHM])
    if payload.get("type") != "access":
        raise jwt.InvalidTokenError("not an access token")
    return payload


def new_refresh_token() -> tuple[str, str, datetime]:
    """Returns (raw token for the app, sha256 hash for the database, expiry)."""
    raw = secrets.token_urlsafe(48)
    expires = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_DAYS)
    return raw, hash_refresh_token(raw), expires


def hash_refresh_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


_PHONE_RE = re.compile(r"^03\d{9}$")


def normalize_phone(value: str) -> str:
    """'0300 1234567', '0300-1234567', '+92 300 1234567', '923001234567' -> '03001234567'.

    Raises ValueError if it is not a Pakistani mobile number.
    """
    digits = re.sub(r"\D", "", value or "")
    if digits.startswith("92") and len(digits) == 12:
        digits = "0" + digits[2:]
    if not _PHONE_RE.match(digits):
        raise ValueError("Enter a Pakistani mobile number like 0300 1234567")
    return digits


def looks_like_phone(value: str) -> bool:
    try:
        normalize_phone(value)
        return True
    except ValueError:
        return False
