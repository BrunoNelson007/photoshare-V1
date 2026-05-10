"""
Security — JWT validation (Auth0), rate limiting, CSP headers, input sanitisation
"""
import re
import time
import httpx
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from slowapi import Limiter
from slowapi.util import get_remote_address

from config import get_settings

settings = get_settings()

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[f"{settings.rate_limit_per_minute}/minute"],
)

bearer_scheme = HTTPBearer(auto_error=False)

_jwks_cache: dict = {}
_jwks_fetched_at: float = 0.0
_JWKS_TTL = 3600


async def _get_jwks() -> dict:
    global _jwks_cache, _jwks_fetched_at
    now = time.time()
    if now - _jwks_fetched_at < _JWKS_TTL and _jwks_cache:
        return _jwks_cache
    jwks_url = f"https://{settings.auth0_domain}/.well-known/jwks.json"
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(jwks_url)
        resp.raise_for_status()
        _jwks_cache = resp.json()
        _jwks_fetched_at = now
    return _jwks_cache


async def _decode_token(token: str) -> dict:
    try:
        jwks = await _get_jwks()
        header = jwt.get_unverified_header(token)
        key = next((k for k in jwks["keys"] if k.get("kid") == header.get("kid")), None)
        if key is None:
            raise HTTPException(status_code=401, detail="Unknown signing key")
        payload = jwt.decode(
            token, key, algorithms=["RS256"],
            audience=settings.auth0_audience,
            issuer=f"https://{settings.auth0_domain}/",
        )
        return payload
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> dict:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return await _decode_token(credentials.credentials)


async def require_creator(user: dict = Depends(get_current_user)) -> dict:
    role_claim = f"https://{get_settings().auth0_domain}/role"
    role = user.get(role_claim, user.get("role", "consumer"))
    if role != "creator":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Creator role required")
    return user


async def require_consumer_or_creator(user: dict = Depends(get_current_user)) -> dict:
    return user


async def security_headers_middleware(request: Request, call_next):
    response = await call_next(request)
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "img-src 'self' https://*.blob.core.windows.net https://*.web.core.windows.net data:; "
        "script-src 'self' 'unsafe-inline' https://cdn.auth0.com; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "connect-src 'self' https://*.auth0.com https://*.azurewebsites.net;"
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    return response


_HTML_TAG_RE = re.compile(r"<[^>]+>")
_SCRIPT_RE   = re.compile(r"(javascript:|data:|vbscript:)", re.IGNORECASE)


def sanitise(value: str, max_len: int = 500) -> str:
    value = _HTML_TAG_RE.sub("", value)
    value = _SCRIPT_RE.sub("", value)
    value = " ".join(value.split())
    return value[:max_len]
