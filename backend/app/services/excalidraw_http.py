"""Async HTTP client for the vendored ``mcp_excalidraw`` Express canvas API."""

from __future__ import annotations

import base64
import logging
from typing import Any

import httpx

log = logging.getLogger(__name__)


class ExcalidrawCanvasClient:
    """Thin wrapper around ``/api/*`` routes documented in ``mcp_excalidraw``."""

    def __init__(self, base_url: str, *, timeout_s: float = 120.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout_s)

    async def health(self) -> dict[str, Any]:
        async with self._client() as client:
            r = await client.get("/health")
            r.raise_for_status()
            return r.json()

    async def clear_canvas(self) -> None:
        async with self._client() as client:
            r = await client.delete("/api/elements/clear")
            if r.status_code not in (200, 204):
                r.raise_for_status()

    async def create_element(self, element: dict[str, Any]) -> dict[str, Any]:
        async with self._client() as client:
            r = await client.post("/api/elements", json=element)
            r.raise_for_status()
            body = r.json()
            return body.get("element") or body

    async def batch_create_elements(self, elements: list[dict[str, Any]]) -> list[dict[str, Any]]:
        async with self._client() as client:
            r = await client.post("/api/elements/batch", json={"elements": elements})
            if r.status_code >= 400:
                log.warning("batch_create_elements failed: %s %s", r.status_code, r.text[:800])
            r.raise_for_status()
            body = r.json()
            return list(body.get("elements") or [])

    async def update_element(self, element_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        async with self._client() as client:
            r = await client.put(f"/api/elements/{element_id}", json=patch)
            if r.status_code >= 400:
                log.warning(
                    "update_element %s failed: %s %s",
                    element_id,
                    r.status_code,
                    (r.text or "")[:800],
                )
            r.raise_for_status()
            body = r.json()
            return body.get("element") or body

    async def get_all_elements(self) -> list[dict[str, Any]]:
        async with self._client() as client:
            r = await client.get("/api/elements")
            r.raise_for_status()
            body = r.json()
            return list(body.get("elements") or [])

    async def export_image_png_base64(self, *, background: bool = True) -> str:
        """Return base64-encoded PNG (no data-URL prefix)."""
        async with self._client() as client:
            r = await client.post(
                "/api/export/image",
                json={"format": "png", "background": background},
            )
            if r.status_code == 503:
                raise RuntimeError(
                    "Canvas export unavailable (no WebSocket client). "
                    "Enable EXCALIDRAW_HEADLESS_AUTOSTART or open the canvas UI."
                )
            r.raise_for_status()
            body = r.json()
            if not body.get("success"):
                raise RuntimeError(body.get("error") or "export failed")
            data = body.get("data")
            if not isinstance(data, str):
                raise RuntimeError("export response missing base64 data")
            return data

    async def export_png_bytes(self, *, background: bool = True) -> bytes:
        b64 = await self.export_image_png_base64(background=background)
        return base64.b64decode(b64)

    async def set_viewport(
        self,
        *,
        scroll_to_content: bool | None = True,
        zoom: float | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if scroll_to_content is not None:
            payload["scrollToContent"] = scroll_to_content
        if zoom is not None:
            payload["zoom"] = zoom
        async with self._client() as client:
            r = await client.post("/api/viewport", json=payload)
            r.raise_for_status()
            return r.json()

    async def create_from_mermaid(self, mermaid_diagram: str) -> dict[str, Any]:
        async with self._client() as client:
            r = await client.post(
                "/api/elements/from-mermaid",
                json={"mermaidDiagram": mermaid_diagram},
            )
            r.raise_for_status()
            return r.json()
