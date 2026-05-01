"""Thin async HTTP façade over the bundled Excalidraw canvas (``mcp_excalidraw``).

Tool implementations mirror MCP behaviour (REST is the MCP transport underneath).
"""

from __future__ import annotations

import math
from typing import Any

import httpx


class ExcalidrawHttpError(RuntimeError):
    pass


def _maybe_float(val: Any) -> float | None:
    if val is None:
        return None
    if isinstance(val, bool):
        return None
    if isinstance(val, (int, float)):
        f = float(val)
        if math.isnan(f) or math.isinf(f):
            return None
        return f
    if isinstance(val, str) and val.strip():
        try:
            return float(val.strip())
        except ValueError:
            return None
    return None


def normalize_mcp_batch_element(el: dict[str, Any]) -> dict[str, Any]:
    """Ensure ``x``/``y`` exist with finite floats (required by MCP CreateElementSchema)."""
    out = dict(el)
    pts_raw = out.get("points")

    x = _maybe_float(out.get("x"))
    y = _maybe_float(out.get("y"))

    rebase_points = False
    if x is None or y is None:
        if isinstance(pts_raw, list) and pts_raw:
            p0 = pts_raw[0]
            ax = 0.0
            ay = 0.0
            if isinstance(p0, (list, tuple)) and len(p0) >= 2:
                ax = _maybe_float(p0[0]) or 0.0
                ay = _maybe_float(p0[1]) or 0.0
            elif isinstance(p0, dict):
                ax = _maybe_float(p0.get("x")) or 0.0
                ay = _maybe_float(p0.get("y")) or 0.0
            if x is None:
                x = ax
                rebase_points = True
            if y is None:
                y = ay
                rebase_points = True
        if x is None:
            x = 0.0
        if y is None:
            y = 0.0

    out["x"] = float(x)
    out["y"] = float(y)

    if rebase_points and isinstance(pts_raw, list) and pts_raw:
        ox, oy = out["x"], out["y"]
        new_pts: list[Any] = []
        for p in pts_raw:
            if isinstance(p, (list, tuple)) and len(p) >= 2:
                new_pts.append(
                    [float(_maybe_float(p[0]) or 0.0) - ox, float(_maybe_float(p[1]) or 0.0) - oy],
                )
            elif isinstance(p, dict):
                new_pts.append(
                    [
                        float(_maybe_float(p.get("x")) or 0.0) - ox,
                        float(_maybe_float(p.get("y")) or 0.0) - oy,
                    ],
                )
            else:
                new_pts.append(p)
        out["points"] = new_pts

    return out


def normalize_mcp_batch_elements(elements: list[Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for i, raw in enumerate(elements):
        if not isinstance(raw, dict):
            raise ExcalidrawHttpError(f"elements[{i}] must be an object, not {type(raw).__name__}")
        out.append(normalize_mcp_batch_element(raw))
    return out


async def elements_clear(client: httpx.AsyncClient) -> dict[str, Any]:
    r = await client.delete("/api/elements/clear")
    r.raise_for_status()
    return r.json()


async def elements_batch(client: httpx.AsyncClient, elements: list[dict[str, Any]]) -> dict[str, Any]:
    normalized = normalize_mcp_batch_elements(elements)
    r = await client.post("/api/elements/batch", json={"elements": normalized})
    if r.status_code >= 400:
        raise ExcalidrawHttpError(r.text[:400])
    return r.json()


async def element_get(client: httpx.AsyncClient, el_id: str) -> dict[str, Any]:
    r = await client.get(f"/api/elements/{el_id}")
    if r.status_code == 404:
        raise ExcalidrawHttpError(f"Element {el_id} not found")
    r.raise_for_status()
    return r.json()


async def element_put(
    client: httpx.AsyncClient, el_id: str, patch: dict[str, Any]
) -> dict[str, Any]:
    r = await client.put(f"/api/elements/{el_id}", json=patch)
    if r.status_code >= 400:
        raise ExcalidrawHttpError(r.text[:400])
    return r.json()


async def element_delete(client: httpx.AsyncClient, el_id: str) -> dict[str, Any]:
    r = await client.delete(f"/api/elements/{el_id}")
    if r.status_code >= 400:
        raise ExcalidrawHttpError(r.text[:400])
    return r.json()


async def elements_list(client: httpx.AsyncClient) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    r = await client.get("/api/elements")
    r.raise_for_status()
    data = r.json()
    els = data.get("elements") or []
    if not isinstance(els, list):
        raise ExcalidrawHttpError("/api/elements shape invalid")
    return els, data


async def files_list(client: httpx.AsyncClient) -> dict[str, Any]:
    r = await client.get("/api/files")
    r.raise_for_status()
    return r.json()


async def export_png(client: httpx.AsyncClient, *, background: bool = True) -> dict[str, Any]:
    r = await client.post("/api/export/image", json={"format": "png", "background": background})
    try:
        return r.json()
    except Exception:
        raise ExcalidrawHttpError(f"PNG export unreadable ({r.status_code}): {r.text[:320]}")


async def viewport_scroll_to_content(client: httpx.AsyncClient) -> dict[str, Any]:
    r = await client.post("/api/viewport", json={"scrollToContent": True})
    try:
        return r.json()
    except Exception:
        raise ExcalidrawHttpError(f"viewport {r.status_code}: {r.text[:320]}")


async def canvas_health_detail(client: httpx.AsyncClient) -> dict[str, Any]:
    r = await client.get("/health")
    r.raise_for_status()
    data = r.json()
    return data if isinstance(data, dict) else {}
