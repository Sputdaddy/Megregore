"""Tests for Megregore security features — auth, rate limiting, CSRF, path traversal."""

import time
from datetime import datetime, timedelta, timezone

import pytest

from megregore.auth import (
    LoginRateLimiter,
    authenticate,
    create_token,
    decode_token,
    hash_password,
    is_token_revoked,
    revoke_token,
    verify_password,
    _revoked_jtis,
)
from megregore.memory import _sanitize_fts


# --- Password Hashing ---

class TestPasswordHashing:
    def test_hash_and_verify(self):
        pw = "testpassword123"
        hashed = hash_password(pw)
        assert hashed != pw
        assert verify_password(pw, hashed)

    def test_wrong_password_fails(self):
        hashed = hash_password("correct")
        assert not verify_password("wrong", hashed)

    def test_different_hashes_for_same_password(self):
        pw = "samepassword"
        h1 = hash_password(pw)
        h2 = hash_password(pw)
        assert h1 != h2  # Different salts


# --- JWT Tokens ---

class TestJWTTokens:
    def test_create_and_decode(self):
        token, expiry = create_token("testuser")
        payload = decode_token(token)
        assert payload is not None
        assert payload["sub"] == "testuser"
        assert "jti" in payload  # Has unique ID for revocation
        assert "exp" in payload
        assert "iat" in payload

    def test_expired_token_rejected(self):
        import jwt as pyjwt
        from megregore.auth import _get_secret
        payload = {
            "sub": "testuser",
            "exp": datetime.now(timezone.utc) - timedelta(hours=1),
            "iat": datetime.now(timezone.utc) - timedelta(hours=2),
            "jti": "test-jti",
        }
        token = pyjwt.encode(payload, _get_secret(), algorithm="HS256")
        assert decode_token(token) is None

    def test_invalid_token_rejected(self):
        assert decode_token("not-a-valid-token") is None
        assert decode_token("") is None


# --- Token Revocation ---

class TestTokenRevocation:
    def setup_method(self):
        _revoked_jtis.clear()

    def test_revoke_and_check(self):
        token, _ = create_token("testuser")
        payload = decode_token(token)
        jti = payload["jti"]

        assert not is_token_revoked(jti)
        revoke_token(jti, payload["exp"])
        assert is_token_revoked(jti)

    def test_revoked_token_decode_fails(self):
        token, _ = create_token("testuser")
        payload = decode_token(token)
        jti = payload["jti"]

        revoke_token(jti, payload["exp"])
        assert decode_token(token) is None

    def test_cleanup_expired_revocations(self):
        # Revoke with an already-expired timestamp
        _revoked_jtis["old-jti"] = time.time() - 3600
        revoke_token("new-jti", time.time() + 3600)
        assert "old-jti" not in _revoked_jtis
        assert "new-jti" in _revoked_jtis


# --- Login Rate Limiter ---

class TestLoginRateLimiter:
    def test_not_locked_initially(self):
        limiter = LoginRateLimiter(max_attempts=3, window_seconds=60)
        assert not limiter.is_locked("1.2.3.4")

    def test_locks_after_max_attempts(self):
        limiter = LoginRateLimiter(max_attempts=3, window_seconds=60)
        for _ in range(3):
            limiter.record_failure("1.2.3.4")
        assert limiter.is_locked("1.2.3.4")

    def test_does_not_lock_below_max(self):
        limiter = LoginRateLimiter(max_attempts=3, window_seconds=60)
        limiter.record_failure("1.2.3.4")
        limiter.record_failure("1.2.3.4")
        assert not limiter.is_locked("1.2.3.4")

    def test_success_clears_failures(self):
        limiter = LoginRateLimiter(max_attempts=3, window_seconds=60)
        limiter.record_failure("1.2.3.4")
        limiter.record_failure("1.2.3.4")
        limiter.record_success("1.2.3.4")
        limiter.record_failure("1.2.3.4")
        assert not limiter.is_locked("1.2.3.4")

    def test_different_ips_independent(self):
        limiter = LoginRateLimiter(max_attempts=2, window_seconds=60)
        limiter.record_failure("1.1.1.1")
        limiter.record_failure("1.1.1.1")
        assert limiter.is_locked("1.1.1.1")
        assert not limiter.is_locked("2.2.2.2")


# --- FTS5 Sanitization ---

class TestFTS5Sanitization:
    def test_strips_special_chars(self):
        assert _sanitize_fts('test*') == 'test'
        assert _sanitize_fts('"hello"') == 'hello'
        assert _sanitize_fts('a(b)c') == 'a b c'
        assert _sanitize_fts('foo:bar') == 'foo bar'

    def test_preserves_normal_text(self):
        assert _sanitize_fts('hello world') == 'hello world'
        assert _sanitize_fts('memory search') == 'memory search'

    def test_strips_injection_attempt(self):
        assert _sanitize_fts('test) OR (1=1') == 'test  OR  1=1'
        assert _sanitize_fts('test" AND "evil') == 'test  AND  evil'

    def test_empty_and_whitespace(self):
        assert _sanitize_fts('') == ''
        assert _sanitize_fts('   ') == ''
        assert _sanitize_fts('***') == ''
