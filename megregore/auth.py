"""
Megregore Authentication — JWT tokens, password hashing, FastAPI dependency.

Single admin user. Password hash stored in data/auth.json.
JWT secret auto-generated and stored in data/.secret.
"""

import json
import logging
import os
import secrets
import stat
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
from uuid import uuid4

import bcrypt
import jwt
from fastapi import HTTPException, Request, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from . import config

logger = logging.getLogger("megregore.auth")

_bearer_scheme = HTTPBearer(auto_error=False)


# --- Login Rate Limiter ---

class LoginRateLimiter:
    """Tracks failed login attempts per IP with exponential backoff lockout.

    After max_attempts failures within window_seconds, the IP is locked out.
    Repeated lockouts escalate: 5min -> 15min -> 60min.
    """

    def __init__(self, max_attempts: int = 5, window_seconds: int = 300):
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        # {ip: [timestamp, ...]}
        self._failures: dict[str, list[float]] = defaultdict(list)
        # {ip: (lockout_until, lockout_count)}
        self._lockouts: dict[str, tuple[float, int]] = {}

    def is_locked(self, ip: str) -> bool:
        """Check if an IP is currently locked out."""
        if ip in self._lockouts:
            lockout_until, _ = self._lockouts[ip]
            if datetime.now(timezone.utc).timestamp() < lockout_until:
                return True
            # Lockout expired — don't clear lockout_count (for escalation)
        return False

    def record_failure(self, ip: str) -> None:
        """Record a failed login attempt. May trigger lockout."""
        import time
        now = time.time()
        cutoff = now - self.window_seconds

        # Clean old failures
        self._failures[ip] = [t for t in self._failures[ip] if t > cutoff]
        self._failures[ip].append(now)

        if len(self._failures[ip]) >= self.max_attempts:
            # Escalate lockout duration
            _, prev_count = self._lockouts.get(ip, (0, 0))
            new_count = prev_count + 1
            # 5min -> 15min -> 60min (capped)
            lockout_minutes = min(60, 5 * (3 ** (new_count - 1)))
            lockout_until = now + lockout_minutes * 60
            self._lockouts[ip] = (lockout_until, new_count)
            self._failures[ip].clear()
            logger.warning(
                "IP %s locked out for %d minutes (attempt #%d)",
                ip, lockout_minutes, new_count,
            )

    def record_success(self, ip: str) -> None:
        """Clear failure tracking on successful login."""
        self._failures.pop(ip, None)
        self._lockouts.pop(ip, None)


login_limiter = LoginRateLimiter()


# --- Token Revocation ---

_revoked_jtis: dict[str, float] = {}  # {jti: expiry_timestamp}


def revoke_token(jti: str, exp: float) -> None:
    """Revoke a token by its JTI. Stores until token's natural expiry."""
    _revoked_jtis[jti] = exp
    _cleanup_revoked()


def is_token_revoked(jti: str) -> bool:
    """Check if a token JTI has been revoked."""
    return jti in _revoked_jtis


def _cleanup_revoked() -> None:
    """Remove expired entries from the revocation set."""
    now = datetime.now(timezone.utc).timestamp()
    expired = [jti for jti, exp in _revoked_jtis.items() if exp < now]
    for jti in expired:
        del _revoked_jtis[jti]


# --- Secret Key Management ---

def _get_secret() -> str:
    """Get the JWT signing secret. Auto-generates if needed."""
    if config.SECRET:
        return config.SECRET

    secret_file = config.SECRET_FILE
    if secret_file.exists():
        return secret_file.read_text().strip()

    # Auto-generate a secure random secret
    secret_file.parent.mkdir(parents=True, exist_ok=True)
    secret = secrets.token_hex(32)
    secret_file.write_text(secret)
    # Restrict file permissions to owner-only (0o600)
    try:
        os.chmod(secret_file, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass  # Windows doesn't support Unix-style permissions
    logger.info("Generated new JWT secret at %s", secret_file)
    return secret


# --- Password Hashing ---

def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    """Verify a password against a bcrypt hash."""
    return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))


# --- JWT Tokens ---

def create_token(username: str) -> tuple[str, datetime]:
    """Create a JWT token with a unique JTI for revocation support.
    Returns (token_string, expiry_datetime)."""
    expiry = datetime.now(timezone.utc) + timedelta(hours=config.TOKEN_EXPIRY_HOURS)
    payload = {
        "sub": username,
        "exp": expiry,
        "iat": datetime.now(timezone.utc),
        "jti": str(uuid4()),
    }
    token = jwt.encode(payload, _get_secret(), algorithm="HS256")
    return token, expiry


def decode_token(token: str) -> Optional[dict]:
    """Decode and validate a JWT token. Checks revocation. Returns payload dict or None."""
    try:
        payload = jwt.decode(token, _get_secret(), algorithms=["HS256"])
        # Check if token has been revoked
        jti = payload.get("jti")
        if jti and is_token_revoked(jti):
            logger.debug("Token revoked (jti=%s)", jti)
            return None
        return payload
    except jwt.ExpiredSignatureError:
        logger.debug("Token expired")
        return None
    except jwt.InvalidTokenError as e:
        logger.debug("Invalid token: %s", e)
        return None


# --- Admin Account Management ---

def is_setup_complete() -> bool:
    """Check if the admin account has been set up."""
    return config.AUTH_FILE.exists()


def get_admin_credentials() -> Optional[dict]:
    """Load admin credentials from auth.json."""
    if not config.AUTH_FILE.exists():
        return None
    try:
        data = json.loads(config.AUTH_FILE.read_text())
        return data
    except (json.JSONDecodeError, IOError) as e:
        logger.error("Failed to read auth.json: %s", e)
        return None


def setup_admin(username: str, password: str) -> dict:
    """Create the admin account. Raises if already set up."""
    if is_setup_complete():
        raise ValueError("Admin account already configured")

    config.AUTH_FILE.parent.mkdir(parents=True, exist_ok=True)
    credentials = {
        "username": username,
        "password_hash": hash_password(password),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    config.AUTH_FILE.write_text(json.dumps(credentials, indent=2))
    logger.info("Admin account created for user '%s'", username)
    return {"username": username, "created_at": credentials["created_at"]}


def authenticate(username: str, password: str) -> Optional[str]:
    """
    Authenticate a user. Returns username on success, None on failure.
    Uses constant-time comparison to prevent timing side-channels.
    """
    creds = get_admin_credentials()
    if creds is None:
        # Still hash to prevent timing leak revealing "no account exists"
        verify_password(password, "$2b$12$" + "0" * 53)
        return None
    if not secrets.compare_digest(creds["username"], username):
        # Still verify password to prevent timing leak
        verify_password(password, creds["password_hash"])
        return None
    if not verify_password(password, creds["password_hash"]):
        return None
    return username


# --- FastAPI Dependency ---

async def require_auth(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(_bearer_scheme),
) -> dict:
    """
    FastAPI dependency that validates the JWT token.
    Checks HttpOnly cookie first, then Authorization header as fallback.
    Returns the decoded token payload.
    Raises 401 if missing/invalid/expired/revoked.
    """
    token = None

    # 1. Try HttpOnly cookie (primary)
    token = request.cookies.get("megregore_token")

    # 2. Fallback to Bearer header
    if not token and credentials is not None:
        token = credentials.credentials

    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")

    payload = decode_token(token)
    if payload is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    return payload
