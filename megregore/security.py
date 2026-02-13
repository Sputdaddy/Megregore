"""Security middleware for FastAPI application.

Provides rate limiting, security headers, CSRF protection, and access logging.
"""

import logging
import secrets
import time
from collections import defaultdict

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from . import config

logger = logging.getLogger("megregore.security")

# Rotating file handler for security events
_security_logger = logging.getLogger("megregore.security.audit")
_security_logger.setLevel(logging.INFO)

if not _security_logger.handlers:
    try:
        from logging.handlers import RotatingFileHandler
        config.DATA_DIR.mkdir(parents=True, exist_ok=True)
        _handler = RotatingFileHandler(
            str(config.SECURITY_LOG),
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=3,
        )
        _handler.setFormatter(logging.Formatter(
            "%(asctime)s | %(levelname)s | %(message)s"
        ))
        _security_logger.addHandler(_handler)
    except Exception:
        pass  # Don't crash the app if log setup fails


def log_security_event(event_type: str, ip: str, detail: str = "") -> None:
    """Log a security event to the audit log."""
    msg = f"{event_type} | ip={ip}"
    if detail:
        msg += f" | {detail}"
    _security_logger.info(msg)


def get_client_ip(request) -> str:
    """Get the real client IP, respecting X-Forwarded-For when behind a trusted proxy."""
    if config.TRUSTED_PROXY:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            # X-Forwarded-For: client, proxy1, proxy2 — leftmost is the original client
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


class RateLimitMiddleware(BaseHTTPMiddleware):
    """In-memory sliding window rate limiter with proxy-aware IP detection."""

    def __init__(self, app, max_requests: int = 60, window_seconds: int = 60):
        super().__init__(app)
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: dict[str, list[float]] = defaultdict(list)

    async def dispatch(self, request, call_next):
        path = request.url.path
        # Skip rate limiting for static files
        if path == "/" or path.startswith(("/css/", "/js/")):
            return await call_next(request)

        client_ip = get_client_ip(request)
        current_time = time.time()
        cutoff_time = current_time - self.window_seconds

        self._requests[client_ip] = [
            t for t in self._requests[client_ip] if t > cutoff_time
        ]

        if len(self._requests[client_ip]) >= self.max_requests:
            log_security_event("rate_limited", client_ip, f"path={path}")
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many requests"}
            )

        self._requests[client_ip].append(current_time)
        return await call_next(request)


class CSRFMiddleware(BaseHTTPMiddleware):
    """Double-submit cookie CSRF protection for mutating requests.

    On login, a non-HttpOnly csrf_token cookie is set.
    For POST/PUT/DELETE requests to /api/*, the middleware validates that
    the X-CSRF-Token header matches the csrf_token cookie.
    """

    # Exempt paths that don't need CSRF (login/setup/auth check)
    EXEMPT_PATHS = {
        "/api/auth/login",
        "/api/auth/setup",
        "/api/auth/status",
        "/api/auth/verify",
        "/api/auth/logout",
    }

    async def dispatch(self, request, call_next):
        # Only check mutating methods on API routes
        if (
            request.method in ("POST", "PUT", "DELETE")
            and request.url.path.startswith("/api/")
            and request.url.path not in self.EXEMPT_PATHS
        ):
            cookie_token = request.cookies.get("megregore_csrf")
            header_token = request.headers.get("x-csrf-token")

            if not cookie_token or not header_token:
                log_security_event("csrf_missing", get_client_ip(request), f"path={request.url.path}")
                return JSONResponse(
                    status_code=403,
                    content={"detail": "CSRF token missing"}
                )

            if not secrets.compare_digest(cookie_token, header_token):
                log_security_event("csrf_invalid", get_client_ip(request), f"path={request.url.path}")
                return JSONResponse(
                    status_code=403,
                    content={"detail": "CSRF token invalid"}
                )

        return await call_next(request)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Adds security headers to all responses."""

    async def dispatch(self, request, call_next):
        response = await call_next(request)

        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # HSTS — only in production/secure mode (behind HTTPS)
        if config.SECURE:
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )

        # CSP — unsafe-eval required for Vue 3 CDN template compilation
        content_type = response.headers.get("content-type", "")
        if "text/html" in content_type:
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-eval' https://unpkg.com https://cdn.jsdelivr.net; "
                "style-src 'self' 'unsafe-inline' https://fonts.bunny.net; "
                "font-src https://fonts.bunny.net; "
                "connect-src 'self'; "
                "img-src 'self' data:;"
            )

        return response
