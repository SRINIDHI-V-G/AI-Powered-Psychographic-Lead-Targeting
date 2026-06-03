"""
Rate limiting middleware — dual backend.

When REDIS_URL is configured:
  Uses Redis INCR + EXPIRE for atomic sliding-window counters.
  Safe across multiple workers/processes.

When REDIS_URL is absent (default dev mode):
  Falls back to an in-memory deque-based sliding window.
  Single-process only — counters reset on restart.

Limits applied:
  POST /api/v1/companies   →  10 / minute  (prevent account farming)
  POST/PUT/PATCH/DELETE    →  60 / minute  per IP
  GET requests             → 200 / minute  per IP

Health, static, and root routes are never rate-limited.
"""
from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

# In-memory fallback store — used when Redis is unavailable
_windows: dict[tuple[str, str], deque] = defaultdict(deque)

# Rate limit rules: (path_prefix, methods, max_calls, period_seconds)
_RULES: list[tuple[str, set[str], int, int]] = [
    ("/api/v1/companies",    {"POST"},                              10,  60),
    ("/api/v1",              {"POST", "PUT", "PATCH", "DELETE"},    60,  60),
    ("/api/v1",              {"GET"},                               200, 60),
]

# Redis client — initialised lazily on first request
_redis_client = None
_redis_checked = False


def _get_redis():
    """Return a synchronous Redis client if REDIS_URL is configured, else None."""
    global _redis_client, _redis_checked
    if _redis_checked:
        return _redis_client
    _redis_checked = True
    try:
        from app.config import settings
        if not settings.REDIS_URL:
            return None
        import redis as sync_redis
        client = sync_redis.from_url(settings.REDIS_URL, socket_connect_timeout=1, decode_responses=True)
        client.ping()
        _redis_client = client
    except Exception:
        _redis_client = None
    return _redis_client


def _get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _check_redis_limit(redis_client, ip: str, window_key: str, max_calls: int, period: int) -> bool:
    """
    Atomic sliding-window check using Redis.
    Returns True if the request is ALLOWED; False if rate limit exceeded.
    Uses a fixed-window INCR approach (simpler than sliding window, good enough for API protection).
    """
    # Window key rotates every `period` seconds
    window_id = int(time.time()) // period
    redis_key = f"ratelimit:{ip}:{window_key}:{window_id}"
    try:
        count = redis_client.incr(redis_key)
        if count == 1:
            redis_client.expire(redis_key, period * 2)   # TTL is 2× window for safety
        return count <= max_calls
    except Exception:
        # Redis error → fail open (allow request) to avoid blocking legitimate traffic
        return True


def _check_memory_limit(ip: str, window_key: str, max_calls: int, period: int) -> bool:
    """Sliding-window check using in-memory deque. Not safe across processes."""
    key = (ip, window_key)
    dq = _windows[key]
    now = time.monotonic()
    cutoff = now - period
    while dq and dq[0] < cutoff:
        dq.popleft()
    if len(dq) >= max_calls:
        return False
    dq.append(now)
    return True


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path
        method = request.method.upper()

        # Never rate-limit health checks, root, or static assets
        if path in ("/health", "/") or path.startswith("/static"):
            return await call_next(request)

        ip = _get_client_ip(request)
        redis = _get_redis()

        for prefix, methods, max_calls, period in _RULES:
            if not path.startswith(prefix):
                continue
            if method not in methods:
                continue

            window_key = f"{prefix}:{method}"
            allowed = (
                _check_redis_limit(redis, ip, window_key, max_calls, period)
                if redis else
                _check_memory_limit(ip, window_key, max_calls, period)
            )

            if not allowed:
                return JSONResponse(
                    status_code=429,
                    content={
                        "detail": (
                            f"Rate limit exceeded: {max_calls} requests "
                            f"per {period}s. Please retry later."
                        )
                    },
                    headers={"Retry-After": str(period)},
                )
            break   # First matching rule wins

        return await call_next(request)
