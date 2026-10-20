import asyncio
from collections import deque
from dataclasses import dataclass
from hashlib import sha256
from time import monotonic

from fastapi import HTTPException, Request, status

from app.core.config import settings


@dataclass
class _Bucket:
    events: deque[float]
    touched: float


class SlidingWindowLimiter:
    """Single-process guard; add gateway or Redis limits for multi-worker deployments."""

    def __init__(self, max_keys: int = 10_000):
        self._buckets: dict[str, _Bucket] = {}
        self._lock = asyncio.Lock()
        self._max_keys = max_keys

    async def check(self, key: str, limit: int, window_seconds: int) -> None:
        now = monotonic()
        cutoff = now - window_seconds
        async with self._lock:
            bucket = self._buckets.setdefault(key, _Bucket(deque(), now))
            while bucket.events and bucket.events[0] <= cutoff:
                bucket.events.popleft()
            if len(bucket.events) >= limit:
                retry_after = max(1, int(window_seconds - (now - bucket.events[0])))
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Too many requests. Please try again later.",
                    headers={"Retry-After": str(retry_after)},
                )
            bucket.events.append(now)
            bucket.touched = now
            if len(self._buckets) > self._max_keys:
                stale = sorted(self._buckets, key=lambda item: self._buckets[item].touched)
                for old_key in stale[: len(self._buckets) - self._max_keys]:
                    self._buckets.pop(old_key, None)

    def clear(self) -> None:
        self._buckets.clear()


limiter = SlidingWindowLimiter()


def client_key(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def account_key(email: str) -> str:
    return sha256(email.strip().lower().encode("utf-8")).hexdigest()


async def check_auth_limit(request: Request, email: str, operation: str) -> None:
    prefix = f"auth:{operation}"
    await limiter.check(
        f"{prefix}:ip:{client_key(request)}",
        settings.auth_rate_limit_requests,
        settings.auth_rate_limit_window_seconds,
    )
    await limiter.check(
        f"{prefix}:account:{account_key(email)}",
        settings.auth_rate_limit_requests,
        settings.auth_rate_limit_window_seconds,
    )


async def check_ai_limit(request: Request, user_id: int) -> None:
    await limiter.check(
        f"ai:user:{user_id}:ip:{client_key(request)}",
        settings.ai_rate_limit_requests,
        settings.ai_rate_limit_window_seconds,
    )
