from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.deps import CurrentUser, DbSession
from app.core.config import settings
from app.core.rate_limit import check_auth_limit
from app.core.security import (
    DUMMY_PASSWORD_HASH,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from app.models import AuthSession, User
from app.schemas.auth import AuthResponse, LoginRequest, RegisterRequest


router = APIRouter(prefix="/auth", tags=["authentication"])


def set_session_cookie(response: Response, user_id: int, session_id: str) -> None:
    response.set_cookie(
        key=settings.auth_cookie_name,
        value=create_access_token(user_id, session_id),
        max_age=settings.jwt_access_token_minutes * 60,
        expires=settings.jwt_access_token_minutes * 60,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )


async def issue_session(response: Response, user_id: int, db: DbSession) -> None:
    session_id = str(uuid4())
    db.add(
        AuthSession(
            id=session_id,
            user_id=user_id,
            expires_at=datetime.now(timezone.utc)
            + timedelta(minutes=settings.jwt_access_token_minutes),
        )
    )
    await db.commit()
    set_session_cookie(response, user_id, session_id)


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest, request: Request, response: Response, db: DbSession):
    await check_auth_limit(request, payload.email, "register")
    user = User(
        email=payload.email.lower(),
        display_name=payload.display_name.strip(),
        password_hash=hash_password(payload.password),
    )
    db.add(user)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="An account with that email already exists") from None
    await db.refresh(user)
    await issue_session(response, user.id, db)
    return AuthResponse(user=user)


@router.post("/login", response_model=AuthResponse)
async def login(payload: LoginRequest, request: Request, response: Response, db: DbSession):
    await check_auth_limit(request, payload.email, "login")
    user = await db.scalar(select(User).where(User.email == payload.email.lower()))
    encoded_hash = user.password_hash if user else DUMMY_PASSWORD_HASH
    valid = verify_password(payload.password, encoded_hash)
    if user is None or not valid or not user.is_active:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    await issue_session(response, user.id, db)
    return AuthResponse(user=user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request, response: Response, db: DbSession):
    token = request.cookies.get(settings.auth_cookie_name)
    if token:
        try:
            user_id, session_id = decode_access_token(token)
            session = await db.scalar(
                select(AuthSession).where(
                    AuthSession.id == session_id,
                    AuthSession.user_id == user_id,
                )
            )
            if session:
                await db.delete(session)
                await db.commit()
        except ValueError:
            pass
    response.delete_cookie(
        settings.auth_cookie_name,
        path="/",
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
    )


@router.get("/me", response_model=AuthResponse)
async def me(user: CurrentUser):
    return AuthResponse(user=user)
