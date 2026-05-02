"""Shared test fixtures: env vars, ES256 keypair, JWKS patch, FastAPI client."""

from __future__ import annotations

import base64
import os
import time
from collections.abc import AsyncIterator, Callable
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio


# Env must be populated before app.config is imported (pydantic-settings validates
# on instantiation). Runs at conftest import, before test collection.
os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_ANON_KEY", "test-anon")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service")
os.environ["ENABLE_MCP_SCENE_DIAGRAM"] = "false"


def _build_es256_keypair() -> tuple[dict, str]:
    """Return (public_jwk, private_pem) for a fresh ES256 keypair."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    private_key = ec.generate_private_key(ec.SECP256R1())
    nums = private_key.public_key().public_numbers()

    def b64url_uint(n: int) -> str:
        return base64.urlsafe_b64encode(n.to_bytes(32, "big")).rstrip(b"=").decode("ascii")

    public_jwk = {
        "kty": "EC",
        "crv": "P-256",
        "x": b64url_uint(nums.x),
        "y": b64url_uint(nums.y),
        "kid": "test-kid",
        "alg": "ES256",
        "use": "sig",
    }
    pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("ascii")
    return public_jwk, pem


_PUBLIC_JWK, _PRIVATE_PEM = _build_es256_keypair()


@pytest.fixture(scope="session")
def test_jwks() -> dict:
    return {"keys": [_PUBLIC_JWK]}


@pytest.fixture(scope="session")
def test_private_pem() -> str:
    return _PRIVATE_PEM


# ---------------------------------------------------------------------------
# Patch _get_jwks so middleware never hits the network.
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _patch_jwks(monkeypatch: pytest.MonkeyPatch, test_jwks: dict) -> None:
    from app.middleware import auth as auth_middleware

    async def fake_get_jwks(force_refresh: bool = False) -> list[dict]:
        return test_jwks["keys"]

    monkeypatch.setattr(auth_middleware, "_get_jwks", fake_get_jwks)


# ---------------------------------------------------------------------------
# JWT factory
# ---------------------------------------------------------------------------

@pytest.fixture
def make_jwt(test_private_pem: str) -> Callable[..., str]:
    """Return a JWT factory signed with the test private key.

    Params:
      user_id: sub claim (UUID string).
      expired: if True, exp is set in the past.
      sub_override: if set, replaces sub entirely (lets tests pass non-UUIDs).
      kid: override the kid header (default 'test-kid').
      alg: override the algorithm (default 'ES256').
      sign_key: override the signing PEM (default the test private key).
    """
    from jose import jwt as jose_jwt

    from app.config import settings

    def _factory(
        user_id: str = "00000000-0000-0000-0000-000000000001",
        expired: bool = False,
        sub_override: str | None = None,
        kid: str = "test-kid",
        alg: str = "ES256",
        sign_key: str | None = None,
    ) -> str:
        now = int(time.time())
        exp = now - 60 if expired else now + 3600
        claims = {
            "iss": f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1",
            "aud": "authenticated",
            "sub": sub_override if sub_override is not None else user_id,
            "email": "test@example.com",
            "iat": now,
            "exp": exp,
        }
        return jose_jwt.encode(
            claims,
            sign_key if sign_key is not None else test_private_pem,
            algorithm=alg,
            headers={"kid": kid, "alg": alg},
        )

    return _factory


# ---------------------------------------------------------------------------
# FastAPI HTTP client
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def client() -> AsyncIterator[Any]:
    import httpx

    from app.main import app

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


# ---------------------------------------------------------------------------
# Supabase user_client mock factories (shared by middleware + routes tests)
# ---------------------------------------------------------------------------

@pytest.fixture
def select_client() -> Callable[[dict | None], AsyncMock]:
    """Factory: returns a user_client mock whose select chain yields profile_row."""

    def _build(profile_row: dict | None) -> AsyncMock:
        response = MagicMock()
        response.data = profile_row

        builder = MagicMock()
        builder.select.return_value = builder
        builder.eq.return_value = builder
        builder.maybe_single.return_value = builder
        builder.execute = AsyncMock(return_value=response)

        sb = MagicMock()
        sb.from_.return_value = builder
        return AsyncMock(return_value=sb)

    return _build


@pytest.fixture
def upsert_client() -> Callable[[dict | None], tuple[AsyncMock, MagicMock]]:
    """Factory: returns (user_client_mock, upsert_mock). upsert_mock records the row arg."""

    def _build(upserted_row: dict | None) -> tuple[AsyncMock, MagicMock]:
        response = MagicMock()
        response.data = [upserted_row] if upserted_row is not None else []

        upsert_chain = MagicMock()
        upsert_chain.execute = AsyncMock(return_value=response)
        upsert_mock = MagicMock(return_value=upsert_chain)

        table = MagicMock()
        table.upsert = upsert_mock

        sb = MagicMock()
        sb.from_.return_value = table
        return AsyncMock(return_value=sb), upsert_mock

    return _build
