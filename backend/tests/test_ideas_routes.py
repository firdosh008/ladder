"""Tests for /ideas CRUD routes."""

from __future__ import annotations

from typing import Any, Callable
from unittest.mock import AsyncMock, MagicMock, patch


def _make_list_client(rows: list[dict]) -> AsyncMock:
    """Fluent chain: from_().select().eq().order().order().limit().execute()."""
    response = MagicMock()
    response.data = rows

    builder = MagicMock()
    builder.select.return_value = builder
    builder.eq.return_value = builder
    builder.order.return_value = builder
    builder.limit.return_value = builder
    builder.execute = AsyncMock(return_value=response)

    client = MagicMock()
    client.from_.return_value = builder
    return AsyncMock(return_value=client)


def _make_insert_client(
    inserted_row: dict | None,
    tail_rows: list[dict] | None = None,
) -> tuple[AsyncMock, MagicMock]:
    """Supports BOTH the auto-position tail SELECT and the final INSERT.

    `tail_rows` — what the pre-insert max(position) lookup returns. Defaults to [].
    """
    insert_resp = MagicMock()
    insert_resp.data = [inserted_row] if inserted_row is not None else []
    insert_chain = MagicMock()
    insert_chain.execute = AsyncMock(return_value=insert_resp)
    insert_mock = MagicMock(return_value=insert_chain)

    tail_resp = MagicMock()
    tail_resp.data = tail_rows if tail_rows is not None else []
    select_chain = MagicMock()
    select_chain.select.return_value = select_chain
    select_chain.eq.return_value = select_chain
    select_chain.order.return_value = select_chain
    select_chain.limit.return_value = select_chain
    select_chain.execute = AsyncMock(return_value=tail_resp)

    table = MagicMock()
    table.insert = insert_mock
    table.select = select_chain.select

    client = MagicMock()
    client.from_.return_value = table
    return AsyncMock(return_value=client), insert_mock


def _make_update_client(updated_row: dict | None) -> AsyncMock:
    response = MagicMock()
    response.data = [updated_row] if updated_row is not None else []

    builder = MagicMock()
    builder.update.return_value = builder
    builder.eq.return_value = builder
    builder.execute = AsyncMock(return_value=response)

    client = MagicMock()
    client.from_.return_value = builder
    return AsyncMock(return_value=client)


def _make_delete_client() -> AsyncMock:
    response = MagicMock()
    response.data = []

    builder = MagicMock()
    builder.delete.return_value = builder
    builder.eq.return_value = builder
    builder.execute = AsyncMock(return_value=response)

    client = MagicMock()
    client.from_.return_value = builder
    return AsyncMock(return_value=client)


# ---------------------------------------------------------------------------
# GET /ideas
# ---------------------------------------------------------------------------

async def test_list_ideas_returns_rows(client: Any, make_jwt: Callable[..., str]) -> None:
    token = make_jwt()
    rows = [
        {"id": "a", "title": "Idea A", "opportunity_score": 90, "status": "new"},
        {"id": "b", "title": "Idea B", "opportunity_score": 70, "status": "new"},
    ]
    with patch("app.routes.ideas.user_client", _make_list_client(rows)):
        resp = await client.get("/ideas", headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 200
    assert resp.json() == {"ideas": rows}


async def test_list_ideas_empty(client: Any, make_jwt: Callable[..., str]) -> None:
    token = make_jwt()
    with patch("app.routes.ideas.user_client", _make_list_client([])):
        resp = await client.get("/ideas", headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 200
    assert resp.json() == {"ideas": []}


async def test_list_ideas_requires_auth(client: Any) -> None:
    resp = await client.get("/ideas")
    assert resp.status_code == 422  # Header(...) missing


# ---------------------------------------------------------------------------
# POST /ideas
# ---------------------------------------------------------------------------

async def test_create_idea_sets_user_id(client: Any, make_jwt: Callable[..., str]) -> None:
    user_id = "11111111-2222-3333-4444-555555555555"
    token = make_jwt(user_id=user_id)
    inserted = {"id": "new-1", "user_id": user_id, "title": "Fresh"}
    user_client_mock, insert_mock = _make_insert_client(inserted)

    with patch("app.routes.ideas.user_client", user_client_mock):
        resp = await client.post(
            "/ideas",
            headers={"Authorization": f"Bearer {token}"},
            json={"title": "Fresh"},
        )

    assert resp.status_code == 201
    assert resp.json() == {"idea": inserted}
    # user_id must be injected from JWT, not from payload
    row = insert_mock.call_args.args[0]
    assert row["user_id"] == user_id
    assert row["title"] == "Fresh"


async def test_create_idea_rejects_blank_title(client: Any, make_jwt: Callable[..., str]) -> None:
    token = make_jwt()
    user_client_mock, _ = _make_insert_client({"id": "x"})

    with patch("app.routes.ideas.user_client", user_client_mock):
        resp = await client.post(
            "/ideas",
            headers={"Authorization": f"Bearer {token}"},
            json={"title": ""},
        )

    assert resp.status_code == 422


async def test_create_idea_clamps_opportunity_score(
    client: Any, make_jwt: Callable[..., str]
) -> None:
    token = make_jwt()
    user_client_mock, _ = _make_insert_client({"id": "x"})

    with patch("app.routes.ideas.user_client", user_client_mock):
        resp = await client.post(
            "/ideas",
            headers={"Authorization": f"Bearer {token}"},
            json={"title": "ok", "opportunity_score": 150},
        )

    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# PATCH /ideas/:id
# ---------------------------------------------------------------------------

async def test_update_idea_partial(client: Any, make_jwt: Callable[..., str]) -> None:
    token = make_jwt()
    updated = {"id": "abc", "title": "New title", "status": "scripting"}

    with patch("app.routes.ideas.user_client", _make_update_client(updated)):
        resp = await client.patch(
            "/ideas/abc",
            headers={"Authorization": f"Bearer {token}"},
            json={"status": "scripting"},
        )

    assert resp.status_code == 200
    assert resp.json() == {"idea": updated}


async def test_update_idea_empty_body_rejected(
    client: Any, make_jwt: Callable[..., str]
) -> None:
    token = make_jwt()
    with patch("app.routes.ideas.user_client", _make_update_client(None)):
        resp = await client.patch(
            "/ideas/abc",
            headers={"Authorization": f"Bearer {token}"},
            json={},
        )

    assert resp.status_code == 400


async def test_update_idea_not_found(client: Any, make_jwt: Callable[..., str]) -> None:
    token = make_jwt()
    with patch("app.routes.ideas.user_client", _make_update_client(None)):
        resp = await client.patch(
            "/ideas/missing",
            headers={"Authorization": f"Bearer {token}"},
            json={"title": "x"},
        )

    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /ideas/:id
# ---------------------------------------------------------------------------

async def test_delete_idea_204(client: Any, make_jwt: Callable[..., str]) -> None:
    token = make_jwt()
    with patch("app.routes.ideas.user_client", _make_delete_client()):
        resp = await client.delete(
            "/ideas/abc",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert resp.status_code == 204


# ---------------------------------------------------------------------------
# Position / ordering
# ---------------------------------------------------------------------------

async def test_list_ideas_orders_by_position(
    client: Any, make_jwt: Callable[..., str]
) -> None:
    """Route returns rows in the order the DB yields; the test asserts the
    query builder was told to order by position first."""
    token = make_jwt()
    rows = [
        {"id": "a", "title": "A", "position": 500, "status": "new"},
        {"id": "b", "title": "B", "position": 2000, "status": "new"},
    ]
    list_client = _make_list_client(rows)

    # Snoop the order() calls by replacing the mock with a tracking variant.
    from unittest.mock import MagicMock as _MM
    from unittest.mock import AsyncMock as _AM
    order_calls: list[tuple[str, bool]] = []

    response = _MM()
    response.data = rows
    builder = _MM()
    builder.select.return_value = builder
    builder.eq.return_value = builder

    def _order(col: str, desc: bool = False, **_kwargs: Any) -> Any:
        order_calls.append((col, desc))
        return builder

    builder.order.side_effect = _order
    builder.limit.return_value = builder
    builder.execute = _AM(return_value=response)

    sb = _MM()
    sb.from_.return_value = builder
    list_client = _AM(return_value=sb)

    with patch("app.routes.ideas.user_client", list_client):
        resp = await client.get("/ideas", headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 200
    # Position must be the FIRST order() call and ascending.
    assert order_calls[0] == ("position", False)


async def test_patch_status_and_position_together(
    client: Any, make_jwt: Callable[..., str]
) -> None:
    token = make_jwt()
    updated = {
        "id": "abc",
        "title": "Moved",
        "status": "scripting",
        "position": 1500.0,
    }
    with patch("app.routes.ideas.user_client", _make_update_client(updated)):
        resp = await client.patch(
            "/ideas/abc",
            headers={"Authorization": f"Bearer {token}"},
            json={"status": "scripting", "position": 1500.0},
        )

    assert resp.status_code == 200
    assert resp.json()["idea"]["position"] == 1500.0


async def test_create_idea_auto_assigns_position_from_tail(
    client: Any, make_jwt: Callable[..., str]
) -> None:
    token = make_jwt()
    inserted = {"id": "x", "title": "Fresh", "status": "new", "position": 4000}
    user_client_mock, insert_mock = _make_insert_client(
        inserted, tail_rows=[{"position": 3000}]
    )

    with patch("app.routes.ideas.user_client", user_client_mock):
        resp = await client.post(
            "/ideas",
            headers={"Authorization": f"Bearer {token}"},
            json={"title": "Fresh"},
        )

    assert resp.status_code == 201
    row = insert_mock.call_args.args[0]
    assert row["position"] == 4000


async def test_create_idea_first_in_status_gets_1000(
    client: Any, make_jwt: Callable[..., str]
) -> None:
    token = make_jwt()
    inserted = {"id": "x", "title": "First", "status": "new", "position": 1000}
    user_client_mock, insert_mock = _make_insert_client(inserted, tail_rows=[])

    with patch("app.routes.ideas.user_client", user_client_mock):
        resp = await client.post(
            "/ideas",
            headers={"Authorization": f"Bearer {token}"},
            json={"title": "First"},
        )

    assert resp.status_code == 201
    row = insert_mock.call_args.args[0]
    assert row["position"] == 1000


async def test_create_idea_explicit_position_skips_tail_lookup(
    client: Any, make_jwt: Callable[..., str]
) -> None:
    token = make_jwt()
    inserted = {"id": "x", "title": "P", "status": "new", "position": 42}
    user_client_mock, insert_mock = _make_insert_client(inserted, tail_rows=[])

    with patch("app.routes.ideas.user_client", user_client_mock):
        resp = await client.post(
            "/ideas",
            headers={"Authorization": f"Bearer {token}"},
            json={"title": "P", "position": 42},
        )

    assert resp.status_code == 201
    row = insert_mock.call_args.args[0]
    assert row["position"] == 42
