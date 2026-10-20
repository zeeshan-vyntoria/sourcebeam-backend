from typing import Annotated
from datetime import datetime, timezone

from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import decode_access_token
from app.db.session import get_db
from app.models import AuthSession, User


DbSession = Annotated[AsyncSession, Depends(get_db)]


async def get_current_user(
    db: DbSession,
    session_token: Annotated[str | None, Cookie(alias=settings.auth_cookie_name)] = None,
) -> User:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required",
    )
    if not session_token:
        raise unauthorized
    try:
        user_id, session_id = decode_access_token(session_token)
    except ValueError:
        raise unauthorized from None
    user = await db.scalar(
        select(User)
        .join(AuthSession, AuthSession.user_id == User.id)
        .where(
            User.id == user_id,
            User.is_active.is_(True),
            AuthSession.id == session_id,
            AuthSession.expires_at > datetime.now(timezone.utc),
        )
    )
    if user is None:
        raise unauthorized
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
