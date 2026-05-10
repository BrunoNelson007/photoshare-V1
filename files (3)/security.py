"""
Security middleware — Advanced Feature #4
-----------------------------------------
• JWT validation against Azure AD B2C JWKS endpoint
• Role extraction (creator / consumer) from token claims
• Rate limiting via slowapi (60 req/min per IP by default)
• Content-Security-Policy + security headers on every response
• Input sanitisation helper used by all routers
"""

import re
import time
import httpx
from functools import lru_cache
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from slowapi import Limiter
from slowapi.util import get_remote_address

from config import get_settings

settings = get_settings()

# ─── Rate limiter (shared instance imported by main.py) ───────────────────────
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[f"{settings.rate_limit_per_minute}/minute"],
)

# ─── Bearer scheme ────────────────────────────────────────────────────────────
bearer_scheme = HTTPBearer(auto_error=False)


# ─── JWKS cache (fetched once per process, refreshed hourly) ─────────────────
_jwks_cache: dict = {}
_jwks_fetched_at: float = 0.0
_JWKS_TTL = 3600  # seconds


async def _get_jwks() -> dict:
    global _jwks_cache, _jwks_fetched_at
    now = time.time()
    if now - _jwks_fetched_at < _JWKS_TTL and _jwks_cache:
        return _jwks_cache

    jwks_url = (
        f"https://{settings.b2c_tenant}.b2clogin.com/"
        f"{settings.b2c_tenant}.onmicrosoft.com/"
        f"{settings.b2c_policy}/discovery/v2.0/keys"
    )
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(jwks_url)
        resp.raise_for_status()
        _jwks_cache = resp.json()
        _jwks_fetched_at = now
    return _jwks_cache


# ─── Token validation ─────────────────────────────────────────────────────────

async def _decode_token(token: str) -> dict:
    """Validate JWT signature, expiry and audience against B2C JWKS."""
    try:
        jwks = await _get_jwks()
        header = jwt.get_unverified_header(token)
        # Find the matching key
        key = next(
            (k for k in jwks["keys"] if k.get("kid") == header.get("kid")),
            None,
        )
        if key is None:
            raise HTTPException(status_code=401, detail="Unknown signing key")

        payload = jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            audience=settings.b2c_client_id,
        )
        return payload
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        )


# ─── Dependencies ─────────────────────────────────────────────────────────────

async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> dict:
    """Require a valid Bearer token. Returns decoded claims."""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return await _decode_token(credentials.credentials)


async def require_creator(user: dict = Depends(get_current_user)) -> dict:
    """Restrict endpoint to creator role only."""
    role = user.get("extension_role", user.get("role", "consumer"))
    if role != "creator":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Creator role required",
        )
    return user


async def require_consumer_or_creator(user: dict = Depends(get_current_user)) -> dict:
    """Allow any authenticated user (creator OR consumer)."""
    return user


# ─── Security headers middleware ──────────────────────────────────────────────

async def security_headers_middleware(request: Request, call_next):
    """
    Inject security headers on every response:
      • Content-Security-Policy   — blocks XSS / injection
      • X-Content-Type-Options    — no MIME sniffing
      • X-Frame-Options           — clickjacking protection
      • Referrer-Policy           — privacy
      • Permissions-Policy        — disable unused browser features
    """
    response = await call_next(request)
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "img-src 'self' https://*.blob.core.windows.net data:; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
        "connect-src 'self' https://*.azurestaticapps.net;"
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = (
        "geolocation=(), microphone=(), camera=()"
    )
    return response


# ─── Input sanitisation ───────────────────────────────────────────────────────

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_SCRIPT_RE = re.compile(r"(javascript:|data:|vbscript:)", re.IGNORECASE)


def sanitise(value: str, max_len: int = 500) -> str:
    """
    Strip HTML tags, remove script-injection patterns,
    normalise whitespace, enforce max length.
    """
    value = _HTML_TAG_RE.sub("", value)
    value = _SCRIPT_RE.sub("", value)
    value = " ".join(value.split())          # collapse whitespace
    return value[:max_len]
