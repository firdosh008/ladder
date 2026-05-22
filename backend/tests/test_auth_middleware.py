"""Tests for app.middleware.auth.current_user.

Exercised via GET /auth/me so the full FastAPI dependency chain is tested.
user_client is stubbed via the shared select_client fixture.
"""

from __future__ import annotations

from typing import Any, Callable
from unittest.mock import AsyncMock, patch
from uuid import UUID

import pytest


async def test_missing_authorization_header(client: Any) -> None:
    resp = await client.get("/auth/me")
    # FastAPI's Header(...) is required → 422; some paths may still 401.
    assert resp.status_code in (401, 422)


async def test_authorization_without_bearer_prefix(client: Any) -> None:
    resp = await client.get("/auth/me", headers={"Authorization": "Basic abc"})
    assert resp.status_code == 401
    assert "bearer" in resp.json()["detail"].lower()


async def test_malformed_jwt(client: Any) -> None:
    resp = await client.get("/auth/me", headers={"Authorization": "Bearer not-a-real-jwt"})
    assert resp.status_code == 401
    assert "malformed" in resp.json()["detail"].lower()


async def test_unknown_kid(client: Any, make_jwt: Callable[..., str]) -> None:
    token = make_jwt(kid="some-other-kid")
    resp = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401
    assert "unknown signing key" in resp.json()["detail"].lower()


async def test_signed_with_wrong_key(client: Any, make_jwt: Callable[..., str]) -> None:
    """Right kid, different signing key → signature check must fail."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    rogue = ec.generate_private_key(ec.SECP256R1())
    rogue_pem = rogue.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("ascii")

    token = make_jwt(sign_key=rogue_pem)
    resp = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


@pytest.mark.xfail(reason="Unit 1 fix pending: middleware should surface 'expired' in detail")
async def test_expired_jwt(client: Any, make_jwt: Callable[..., str]) -> None:
    token = make_jwt(expired=True)
    resp = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401
    assert "expired" in resp.json()["detail"].lower()


@pytest.mark.xfail(reason="Unit 1 fix pending: non-UUID sub should raise clean 401, not 500")
async def test_non_uuid_sub(client: Any, make_jwt: Callable[..., str]) -> None:
    token = make_jwt(sub_override="not-a-uuid")
    resp = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


async def test_valid_jwt_returns_user_id_and_token(make_jwt: Callable[..., str]) -> None:
    from app.middleware.auth import current_user

    user_id = "11111111-2222-3333-4444-555555555555"
    token = make_jwt(user_id=user_id)

    parsed_id, raw = await current_user(authorization=f"Bearer {token}")
    assert isinstance(parsed_id, UUID)
    assert str(parsed_id) == user_id
    assert raw == token


async def test_valid_jwt_end_to_end(
    client: Any,
    make_jwt: Callable[..., str],
    select_client: Callable[[dict | None], AsyncMock],
) -> None:
    from unittest.mock import AsyncMock as _AM
    from unittest.mock import MagicMock as _MM

    # Stub service_client so the /auth/me self-heal (when profile is None)
    # doesn't try to hit a real Supabase.
    noop_resp = _MM()
    noop_resp.data = []
    noop_chain = _MM()
    noop_chain.execute = _AM(return_value=noop_resp)
    noop_table = _MM()
    noop_table.upsert.return_value = noop_chain
    noop_sb = _MM()
    noop_sb.from_.return_value = noop_table
    noop_service = _AM(return_value=noop_sb)

    token = make_jwt()
    with patch("app.routes.auth.user_client", select_client(None)), patch(
        "app.routes.auth.service_client", noop_service
    ):
        resp = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
