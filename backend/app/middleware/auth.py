import time
from uuid import UUID

import httpx
from fastapi import Header, HTTPException, status
from jose import JWTError, jwt

from app.config import settings


JWKS_URL = f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1/.well-known/jwks.json"
_JWKS_TTL_SECONDS = 600
_ALLOWED_ALGS = {"ES256", "RS256"}

_jwks_cache: dict = {"keys": [], "fetched_at": 0.0}


async def _get_jwks(force_refresh: bool = False) -> list[dict]:
    now = time.time()
    fresh = now - _jwks_cache["fetched_at"] < _JWKS_TTL_SECONDS
    if not force_refresh and _jwks_cache["keys"] and fresh:
        return _jwks_cache["keys"]
    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.get(JWKS_URL)
        resp.raise_for_status()
        data = resp.json()
    _jwks_cache["keys"] = data.get("keys", [])
    _jwks_cache["fetched_at"] = now
    return _jwks_cache["keys"]


async def _find_key(kid: str) -> dict | None:
    for jwk in await _get_jwks():
        if jwk.get("kid") == kid:
            return jwk
    for jwk in await _get_jwks(force_refresh=True):
        if jwk.get("kid") == kid:
            return jwk
    return None


async def current_user(authorization: str = Header(...)) -> tuple[UUID, str]:
    """Verify the Supabase JWT from the Authorization header.

    Returns (user_id, raw_jwt). The raw JWT is needed to build a user-scoped
    Supabase client so RLS applies to every downstream query.
    """
    if not authorization.startswith("Bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")

    token = authorization.removeprefix("Bearer ").strip()

    try:
        header = jwt.get_unverified_header(token)
    except JWTError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"Malformed token: {e}") from e

    kid = header.get("kid")
    if not kid:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token missing kid header")

    jwk = await _find_key(kid)
    if not jwk:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Unknown signing key")

    alg = jwk.get("alg") or header.get("alg")
    if alg not in _ALLOWED_ALGS:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"Unsupported alg: {alg}")

    try:
        payload = jwt.decode(
            token,
            jwk,
            algorithms=[alg],
            audience="authenticated",
        )
    except JWTError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"Invalid token: {e}") from e

    sub = payload.get("sub")
    if not sub:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token missing sub claim")

    return UUID(sub), token
