"""WebSocket JWT verification — token arrives as a query-string param.

Browsers cannot set custom Authorization headers on `new WebSocket()`, so the
client appends `?token=<jwt>` on connect. Verification reuses the JWKS cache
+ algorithm rules from middleware/auth.py so the security properties are
identical to HTTP routes.
"""

from __future__ import annotations

from uuid import UUID

from jose import JWTError, jwt
from jose.exceptions import ExpiredSignatureError

from app.middleware.auth import _ALLOWED_ALGS, _find_key


class WsAuthError(Exception):
    """Raised when the token cannot be verified. The WebSocket route closes
    with code 4401 (application-level 'unauthorized') when this surfaces."""


async def verify_ws_token(token: str | None) -> tuple[UUID, str]:
    """Return (user_id, raw_jwt) or raise WsAuthError."""
    if not token:
        raise WsAuthError("missing token")

    try:
        header = jwt.get_unverified_header(token)
    except JWTError as e:
        raise WsAuthError(f"malformed token: {e}") from e

    kid = header.get("kid")
    if not kid:
        raise WsAuthError("token missing kid header")

    jwk = await _find_key(kid)
    if not jwk:
        raise WsAuthError("unknown signing key")

    alg = jwk.get("alg") or header.get("alg")
    if alg not in _ALLOWED_ALGS:
        raise WsAuthError(f"unsupported alg: {alg}")

    try:
        payload = jwt.decode(
            token,
            jwk,
            algorithms=[alg],
            audience="authenticated",
        )
    except ExpiredSignatureError as e:
        raise WsAuthError("token expired") from e
    except JWTError as e:
        raise WsAuthError(f"invalid token: {e}") from e

    sub = payload.get("sub")
    if not sub:
        raise WsAuthError("token missing sub claim")

    try:
        user_id = UUID(sub)
    except ValueError as e:
        raise WsAuthError("token sub is not a valid UUID") from e

    return user_id, token
