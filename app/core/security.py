from datetime import datetime, timedelta, timezone

import jwt
from jwt import InvalidTokenError
from pwdlib import PasswordHash

from app.core.config import settings


password_hash = PasswordHash.recommended()
DUMMY_PASSWORD_HASH = password_hash.hash("not-the-real-password")


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, encoded_hash: str) -> bool:
    return password_hash.verify(password, encoded_hash)


def create_access_token(user_id: int, session_id: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": f"user:{user_id}",
        "jti": session_id,
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_access_token_minutes),
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> tuple[int, str]:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
            issuer=settings.jwt_issuer,
            audience=settings.jwt_audience,
            options={"require": ["sub", "jti", "iat", "exp", "iss", "aud"]},
        )
        subject = payload["sub"]
        if not isinstance(subject, str) or not subject.startswith("user:"):
            raise InvalidTokenError("Invalid subject")
        session_id = payload["jti"]
        if not isinstance(session_id, str) or not session_id:
            raise InvalidTokenError("Invalid session identifier")
        return int(subject.removeprefix("user:")), session_id
    except (InvalidTokenError, ValueError, TypeError) as exc:
        raise ValueError("Invalid session") from exc
