from datetime import datetime, timedelta, timezone

import jwt
from pwdlib import PasswordHash
from app.core.config import settings


password_hash = PasswordHash.recommended()


JWT_SECRET_KEY = settings.jwt_secret_key
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = settings.access_token_expire_minutes
REFRESH_TOKEN_EXPIRE_DAYS = settings.refresh_token_expire_days


# -------------------------
# PASSWORD HASHING
# -------------------------

def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(
    plain_password: str,
    hashed_password: str,
) -> bool:
    return password_hash.verify(
        plain_password,
        hashed_password,
    )


# -------------------------
# ACCESS TOKEN
# -------------------------

def create_access_token(user_id: int) -> str:
    now = datetime.now(timezone.utc)

    payload = {
        "sub": str(user_id),
        "type": "access",
        "iat": now,
        "exp": now + timedelta(
            minutes=ACCESS_TOKEN_EXPIRE_MINUTES
        ),
    }

    return jwt.encode(
        payload,
        JWT_SECRET_KEY,
        algorithm=JWT_ALGORITHM,
    )


# -------------------------
# REFRESH TOKEN
# -------------------------

def create_refresh_token(
    user_id: int,
    session_id: str,
    refresh_jti: str,
) -> str:
    now = datetime.now(timezone.utc)

    payload = {
        "sub": str(user_id),
        "type": "refresh",
        "sid": session_id,
        "jti": refresh_jti,
        "iat": now,
        "exp": now + timedelta(
            days=REFRESH_TOKEN_EXPIRE_DAYS
        ),
    }

    return jwt.encode(
        payload,
        JWT_SECRET_KEY,
        algorithm=JWT_ALGORITHM,
    )


# -------------------------
# DECODE / VERIFY TOKEN
# -------------------------

def decode_token(token: str) -> dict:
    return jwt.decode(
        token,
        JWT_SECRET_KEY,
        algorithms=[JWT_ALGORITHM],
    )
