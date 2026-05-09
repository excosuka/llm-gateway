import time
from dataclasses import dataclass

from fastapi import Depends, HTTPException, status

from gateway.auth_service import get_authenticated_key
from gateway.config import ApiKeyConfig, RateLimitConfig


@dataclass
class BucketState:
    tokens: float
    last_update: float

class RateLimiter:
    def __init__(self) -> None:
        self._buckets: dict[str, BucketState] = {}

    def try_acquire(self, key: str, config: RateLimitConfig) -> bool:
        now = time.monotonic()
        bucket_state = self._buckets.get(key)

        if bucket_state is None:
            bucket_state = BucketState(tokens=config.bucket_size, last_update=now)
            self._buckets[key] = bucket_state

        dt = now - bucket_state.last_update
        bucket_state.tokens = min(
            config.bucket_size,
            bucket_state.tokens + dt * config.tokens_per_second,
        )
        bucket_state.last_update = now

        if bucket_state.tokens >= 1:
            bucket_state.tokens -= 1
            return True
        return False

_rate_limiter: RateLimiter | None = None

def init_rate_limiter(limiter: RateLimiter) -> None:
    global _rate_limiter
    _rate_limiter = limiter


def enforce_rate_limit(
    api_key: ApiKeyConfig = Depends(get_authenticated_key),
) -> ApiKeyConfig:
    """
    FastAPI dependency. Проверяет rate limit, бросает 429 при превышении.
    Возвращает ApiKeyConfig (чтобы дальше можно было использовать в роуте).
    """
    if _rate_limiter is None:
        raise RuntimeError("RateLimiter is not initialized")
    if not _rate_limiter.try_acquire(api_key.key, api_key.rate_limit):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded",
        )
    return api_key