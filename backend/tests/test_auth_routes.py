"""Tests for /auth/me and /auth/onboard.

All Supabase calls go through user_client, which we patch to a MagicMock
whose fluent `.from_(...).select(...).eq(...).maybe_single().execute()` /
`.from_(...).upsert(...).execute()` chain returns configured responses.
"""

from __future__ import annotations

from typing import Any, Callable
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Mock factories
# ---------------------------------------------------------------------------

def _make_select_client(profile_row: dict | None) -> AsyncMock:
    """user_client mock that returns profile_row from a select chain."""
    response = MagicMock()
    response.data = profile_row

    builder = MagicMock()
    builder.select.return_value = builder
    builder.eq.return_value = builder
    builder.maybe_single.return_value = builder
    builder.execute = AsyncMock(return_value=response)

    client = MagicMock()
    client.from_.return_value = builder
    return AsyncMock(return_value=client)


def _make_upsert_client(upserted_row: dict | None) -> tuple[AsyncMock, MagicMock]:
    """Returns (user_client_mock, upsert_mock).

    upsert_mock records the row argument so tests can inspect it.
    """
    response = MagicMock()
    response.data = [upserted_row] if upserted_row is not None else []

    upsert_mock = MagicMock()
    upsert_execute = AsyncMock(return_value=response)
    # .upsert(row, on_conflict=...).execute()
    upsert_chain = MagicMock()
    upsert_chain.execute = upsert_execute
    upsert_mock.return_value = upsert_chain

    table = MagicMock()
    table.upsert = upsert_mock

    client = MagicMock()
    client.from_.return_value = table
    return AsyncMock(return_value=client), upsert_mock


# ---------------------------------------------------------------------------
# GET /auth/me
# ---------------------------------------------------------------------------

async def test_me_returns_expected_shape(client: Any, make_jwt: Callable[..., str]) -> None:
    user_id = "11111111-2222-3333-4444-555555555555"
    token = make_jwt(user_id=user_id)
    profile = {
        "user_id": user_id,
        "display_name": "Ada",
        "onboarded_at": "2024-01-01T00:00:00+00:00",
    }
    with patch("app.routes.auth.user_client", _make_select_client(profile)):
        resp = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 200
    body = resp.json()
    # user_id, profile, onboarded are guaranteed; email may land in profile or top-level
    # depending on Unit 1's changes. Spec requires the key exist.
    for key in ("user_id", "profile", "onboarded"):
        assert key in body, f"missing key: {key}"
    assert body["user_id"] == user_id
    assert body["profile"] == profile


@pytest.mark.xfail(reason="Unit 1 fix pending: /auth/me should include 'email' from JWT claims")
async def test_me_includes_email(client: Any, make_jwt: Callable[..., str]) -> None:
    token = make_jwt()
    with patch("app.routes.auth.user_client", _make_select_client(None)):
        resp = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 200
    assert "email" in resp.json()


async def test_me_onboarded_true_when_timestamp_set(
    client: Any, make_jwt: Callable[..., str]
) -> None:
    token = make_jwt()
    profile = {"onboarded_at": "2024-01-01T00:00:00+00:00"}
    with patch("app.routes.auth.user_client", _make_select_client(profile)):
        resp = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 200
    assert resp.json()["onboarded"] is True


async def test_me_onboarded_false_when_timestamp_null(
    client: Any, make_jwt: Callable[..., str]
) -> None:
    token = make_jwt()
    profile = {"onboarded_at": None, "display_name": "not-yet"}
    with patch("app.routes.auth.user_client", _make_select_client(profile)):
        resp = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 200
    assert resp.json()["onboarded"] is False


async def test_me_onboarded_false_when_no_profile(
    client: Any, make_jwt: Callable[..., str]
) -> None:
    token = make_jwt()
    with patch("app.routes.auth.user_client", _make_select_client(None)):
        resp = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["onboarded"] is False
    assert body["profile"] is None


# ---------------------------------------------------------------------------
# POST /auth/onboard
# ---------------------------------------------------------------------------

async def test_onboard_valid_payload(client: Any, make_jwt: Callable[..., str]) -> None:
    user_id = "11111111-2222-3333-4444-555555555555"
    token = make_jwt(user_id=user_id)

    upserted = {
        "user_id": user_id,
        "display_name": "Ada",
        "positioning": "makers",
        "audience": "indie devs",
        "voice": "friendly",
        "creators_followed": ["swyx"],
        "things_to_avoid": "hype",
        "onboarded_at": "2024-01-01T00:00:00+00:00",
    }
    user_client_mock, _upsert_mock = _make_upsert_client(upserted)

    payload = {
        "display_name": "Ada",
        "positioning": "makers",
        "audience": "indie devs",
        "voice": "friendly",
        "creators_followed": ["swyx"],
        "things_to_avoid": "hype",
    }
    with patch("app.routes.auth.user_client", user_client_mock):
        resp = await client.post(
            "/auth/onboard",
            headers={"Authorization": f"Bearer {token}"},
            json=payload,
        )

    assert resp.status_code == 200
    assert resp.json() == {"profile": upserted}


@pytest.mark.xfail(reason="Unit 1 fix pending: Pydantic model should reject missing display_name")
async def test_onboard_missing_display_name_returns_422(
    client: Any, make_jwt: Callable[..., str]
) -> None:
    token = make_jwt()
    user_client_mock, _ = _make_upsert_client({"user_id": "x"})

    with patch("app.routes.auth.user_client", user_client_mock):
        resp = await client.post(
            "/auth/onboard",
            headers={"Authorization": f"Bearer {token}"},
            json={"positioning": "makers"},  # missing display_name
        )

    assert resp.status_code == 422


@pytest.mark.xfail(reason="Unit 1 fix pending: onboarded_at must be ISO string, not literal 'now()'")
async def test_onboard_writes_iso_timestamp_not_now_string(
    client: Any, make_jwt: Callable[..., str]
) -> None:
    token = make_jwt()
    user_client_mock, upsert_mock = _make_upsert_client({"user_id": "x"})

    with patch("app.routes.auth.user_client", user_client_mock):
        resp = await client.post(
            "/auth/onboard",
            headers={"Authorization": f"Bearer {token}"},
            json={"display_name": "Ada"},
        )

    assert resp.status_code == 200
    # First positional arg to .upsert() is the row dict.
    assert upsert_mock.called, "upsert was not invoked"
    row = upsert_mock.call_args.args[0]
    onboarded_at = row["onboarded_at"]
    # Must NOT be the literal Postgres expression string.
    assert onboarded_at != "now()"
    # Must be ISO-8601 parseable.
    from datetime import datetime

    datetime.fromisoformat(str(onboarded_at).replace("Z", "+00:00"))
