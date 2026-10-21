import jwt

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import (
    APIRouter,
    Cookie,
    Depends,
    HTTPException,
    Response,
    status,
)
from app.core.dependencies import get_current_user
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import (
    REFRESH_TOKEN_EXPIRE_DAYS,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.core.config import settings
from app.database import get_db
from app.models.auth_session import AuthSession
from app.models.user import User
from app.schemas.user import (
    TokenResponse,
    UserCreate,
    UserLogin,
    UserResponse,
)


router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)


# -------------------------
# REGISTER
# -------------------------

@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
def register_user(
    user_data: UserCreate,
    db: Session = Depends(get_db),
):
    existing_user = db.scalar(
        select(User).where(User.email == user_data.email)
    )

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email is already registered",
        )

    new_user = User(
        email=user_data.email,
        hashed_password=hash_password(user_data.password),
        full_name=user_data.full_name,
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return new_user


# -------------------------
# LOGIN
# -------------------------

@router.post(
    "/login",
    response_model=TokenResponse,
)
def login_user(
    user_data: UserLogin,
    response: Response,
    db: Session = Depends(get_db),
):
    user = db.scalar(
        select(User).where(User.email == user_data.email)
    )

    if not user or not verify_password(
        user_data.password,
        user.hashed_password,
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive",
        )

    session_id = str(uuid4())
    refresh_jti = str(uuid4())

    expires_at = datetime.now(timezone.utc) + timedelta(
        days=REFRESH_TOKEN_EXPIRE_DAYS
    )

    auth_session = AuthSession(
        id=session_id,
        user_id=user.id,
        refresh_jti=refresh_jti,
        expires_at=expires_at,
    )

    db.add(auth_session)
    db.commit()

    access_token = create_access_token(user.id)

    refresh_token = create_refresh_token(
        user_id=user.id,
        session_id=session_id,
        refresh_jti=refresh_jti,
    )

    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        max_age=REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
        path="/auth",
    )

    return {
        "access_token": access_token,
        "token_type": "bearer",
    }


# -------------------------
# REFRESH + ROTATION
# -------------------------

@router.post(
    "/refresh",
    response_model=TokenResponse,
)
def refresh_access_token(
    response: Response,
    refresh_token: str | None = Cookie(default=None),
    db: Session = Depends(get_db),
):
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token missing",
        )

    try:
        payload = decode_token(refresh_token)

        if payload.get("type") != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type",
            )

        user_id = int(payload["sub"])
        session_id = payload["sid"]
        refresh_jti = payload["jti"]

    except (jwt.InvalidTokenError, KeyError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    # Find the login session
    # Serialize refresh rotation for a session so concurrent refresh requests
    # cannot both accept the same refresh JTI.
    auth_session = db.scalar(
        select(AuthSession)
        .where(AuthSession.id == session_id)
        .with_for_update()
    )

    if not auth_session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session not found",
        )

    # Session must belong to the same user
    if auth_session.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid session",
        )

    # Session must not have been revoked
    if auth_session.revoked_at is not None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session has been revoked",
        )

    # Session must not be expired
    if auth_session.expires_at <= datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session has expired",
        )

    # The JTI in the JWT must be the current JTI in the database.
    #
    # If it is different, an old refresh token may have been reused.
    if auth_session.refresh_jti != refresh_jti:
        auth_session.revoked_at = datetime.now(timezone.utc)
        db.commit()

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token reuse detected",
        )

    user = db.get(User, user_id)

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not available",
        )

    # -------------------------
    # ROTATE REFRESH TOKEN
    # -------------------------

    new_refresh_jti = str(uuid4())

    auth_session.refresh_jti = new_refresh_jti

    db.commit()

    new_access_token = create_access_token(user.id)

    new_refresh_token = create_refresh_token(
        user_id=user.id,
        session_id=auth_session.id,
        refresh_jti=new_refresh_jti,
    )

    # Replace old refresh-token cookie
    response.set_cookie(
        key="refresh_token",
        value=new_refresh_token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        max_age=REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
        path="/auth",
    )

    return {
        "access_token": new_access_token,
        "token_type": "bearer",
    }

# -------------------------
# LOGOUT
# -------------------------

@router.post("/logout")
def logout_user(
    response: Response,
    refresh_token: str | None = Cookie(default=None),
    db: Session = Depends(get_db),
):
    if refresh_token:
        try:
            payload = decode_token(refresh_token)

            if payload.get("type") == "refresh":
                session_id = payload.get("sid")

                if session_id:
                    auth_session = db.get(
                        AuthSession,
                        session_id,
                    )

                    if (
                        auth_session
                        and auth_session.revoked_at is None
                    ):
                        auth_session.revoked_at = datetime.now(
                            timezone.utc
                        )
                        db.commit()

        except jwt.InvalidTokenError:
            pass

    # Remove refresh-token cookie from browser
    response.delete_cookie(
        key="refresh_token",
        path="/auth",
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
    )

    return {
        "message": "Logged out successfully"
    }

# -------------------------
# CURRENT USER
# -------------------------

@router.get(
    "/me",
    response_model=UserResponse,
)
def get_me(
    current_user: User = Depends(get_current_user),
):
    return current_user
