"""Manage the vendored ``mcp_excalidraw`` canvas server + optional Playwright tab.

Spawns ``node dist/server.js`` using synchronous ``subprocess.Popen`` from a thread
(avoids Windows asyncio subprocess limitations). Runs ``npm ci`` / ``npm install``
plus ``npm run build`` when ``dist/`` is missing (same bootstrap as commit
``33d206d``). Optionally starts ``scripts/headless-canvas.mjs`` so PNG export has a
WebSocket client.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from app.config import settings

log = logging.getLogger(__name__)

_canvas_proc: subprocess.Popen[bytes] | None = None
_headless_proc: subprocess.Popen[bytes] | None = None
_we_started_canvas = False
_we_started_headless = False
_build_lock = asyncio.Lock()


def default_vendor_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent / "vendor" / "mcp_excalidraw"


def boot_error_message(exc: BaseException) -> str:
    """Stable message when ``str(exc)`` is empty (e.g. bare ``NotImplementedError``)."""
    text = str(exc).strip()
    if text:
        return text
    return f"{type(exc).__name__}: {exc!r}"


def _resolve_vendor(vendor: Path | None) -> Path:
    if vendor is not None:
        return vendor.resolve()
    raw = settings.EXCALIDRAW_VENDOR_ROOT.strip()
    if raw:
        return Path(raw).resolve()
    return default_vendor_root()


def _npm_cmd(*args: str) -> list[str]:
    npm = shutil.which("npm.cmd") if sys.platform == "win32" else shutil.which("npm")
    if not npm:
        raise RuntimeError(
            "npm is required to build the Excalidraw canvas. Install Node.js 18+ "
            "and ensure npm is on PATH."
        )
    return [npm, *args]


def _node_cmd() -> str:
    exe = shutil.which("node") or shutil.which("node.exe")
    if not exe:
        raise RuntimeError(
            "Node.js is required — install Node 18+ and ensure `node` is on PATH."
        )
    return exe


def _stderr_tail(path: Path, limit: int = 6000) -> str:
    try:
        data = path.read_bytes()
        return data[-limit:].decode(errors="replace")
    except OSError:
        return ""


def _build_complete(vendor: Path) -> bool:
    idx = vendor / "dist" / "frontend" / "index.html"
    srv = vendor / "dist" / "server.js"
    return idx.is_file() and srv.is_file()


async def ensure_vendor_build(vendor: Path) -> None:
    """Ensure ``npm ci`` / ``install`` + ``npm run build`` produced ``dist/``."""
    async with _build_lock:
        if _build_complete(vendor):
            return
        loop = asyncio.get_running_loop()

        def _run() -> None:
            lockfile = vendor / "package-lock.json"
            if lockfile.is_file():
                subprocess.run(_npm_cmd("ci"), cwd=str(vendor), check=True)
            else:
                subprocess.run(_npm_cmd("install"), cwd=str(vendor), check=True)
            subprocess.run(_npm_cmd("run", "build"), cwd=str(vendor), check=True)

        await loop.run_in_executor(None, _run)
        if not _build_complete(vendor):
            raise RuntimeError(
                f"Expected dist bundle under {vendor} after npm build — check Node/npm logs."
            )


def _parse_http_base(http_base: str) -> tuple[str, int]:
    u = urlparse(http_base if "://" in http_base else f"http://{http_base}")
    host = u.hostname or "127.0.0.1"
    port = u.port or 3000
    return host, port


async def _health_payload(base_url: str) -> dict[str, Any] | None:
    url = f"{base_url.rstrip('/')}/health"
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            r = await client.get(url)
            if r.status_code != 200:
                return None
            return r.json()
    except Exception:
        return None


async def wait_for_canvas_http(base_url: str, *, timeout_s: float = 60.0) -> None:
    deadline = asyncio.get_event_loop().time() + timeout_s
    while asyncio.get_event_loop().time() < deadline:
        data = await _health_payload(base_url)
        if data and data.get("status") == "healthy":
            return
        await asyncio.sleep(0.35)
    raise TimeoutError(f"Excalidraw canvas did not become healthy at {base_url}")


async def wait_for_websocket_clients(
    base_url: str,
    *,
    timeout_s: float,
    min_clients: int = 1,
) -> None:
    deadline = asyncio.get_event_loop().time() + timeout_s
    while asyncio.get_event_loop().time() < deadline:
        data = await _health_payload(base_url)
        if data and int(data.get("websocket_clients") or 0) >= min_clients:
            return
        await asyncio.sleep(0.35)
    raise TimeoutError(
        f"No WebSocket client connected to canvas within {timeout_s}s. "
        "PNG export requires one browser tab on the canvas. "
        "Fix: set EXCALIDRAW_HEADLESS_AUTOSTART=true and run "
        "`cd <vendor>/mcp_excalidraw && npx playwright install chromium`, "
        f"or open {base_url.rstrip('/')}/ in a normal browser while generating."
    )


async def _stop_canvas_sync() -> None:
    global _canvas_proc, _we_started_canvas
    if _canvas_proc is None:
        return
    proc = _canvas_proc
    _canvas_proc = None
    try:
        proc.terminate()
        await asyncio.wait_for(asyncio.to_thread(proc.wait), timeout=8.0)
    except TimeoutError:
        proc.kill()
    except ProcessLookupError:
        pass
    _we_started_canvas = False


async def _stop_headless_sync() -> None:
    global _headless_proc, _we_started_headless
    if _headless_proc is None:
        return
    proc = _headless_proc
    _headless_proc = None
    try:
        proc.terminate()
        await asyncio.wait_for(asyncio.to_thread(proc.wait), timeout=5.0)
    except TimeoutError:
        proc.kill()
    except ProcessLookupError:
        pass
    _we_started_headless = False


async def _ensure_playwright_ws_client(*, base: str, vendor: Path | None) -> None:
    """Ensure ``/health`` reports websocket_clients >= 1 when headless autostart is enabled."""
    global _headless_proc, _we_started_headless

    if not settings.EXCALIDRAW_HEADLESS_AUTOSTART:
        log.warning(
            "EXCALIDRAW_HEADLESS_AUTOSTART=false — PNG export needs a browser tab at %s",
            base,
        )
        return

    payload = await _health_payload(base)
    if payload and int(payload.get("websocket_clients") or 0) >= 1:
        log.debug("Canvas already has %s WebSocket client(s)", payload.get("websocket_clients"))
        return

    root = _resolve_vendor(vendor)
    headless_script = root / "scripts" / "headless-canvas.mjs"
    if not headless_script.is_file():
        raise RuntimeError(
            f"Missing {headless_script}. Cannot attach a headless export client."
        )

    node = _node_cmd()
    env_h = os.environ.copy()
    env_h["EXCALIDRAW_HEADLESS_URL"] = base.rstrip("/")

    need_spawn = _headless_proc is None or (_headless_proc.poll() is not None)
    if need_spawn:
        log.info("Starting headless canvas tab via Playwright (required for PNG export)")

        def _spawn_headless() -> subprocess.Popen[bytes]:
            kw: dict[str, Any] = {
                "cwd": str(root),
                "env": env_h,
                "stdout": subprocess.DEVNULL,
                "stderr": subprocess.DEVNULL,
            }
            if sys.platform == "win32":
                kw["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            return subprocess.Popen([node, str(headless_script)], **kw)

        _headless_proc = await asyncio.to_thread(_spawn_headless)
        _we_started_headless = True

    await asyncio.sleep(1.5)
    if _headless_proc is not None and _headless_proc.poll() is not None:
        raise RuntimeError(
            "Playwright headless canvas exited immediately (exit "
            f"code {_headless_proc.poll()}). From the vendor folder run: "
            f"cd {root} && npx playwright install chromium"
        )

    await wait_for_websocket_clients(
        base,
        timeout_s=settings.EXCALIDRAW_HEADLESS_CONNECT_TIMEOUT_S,
        min_clients=1,
    )


async def ensure_canvas_running(
    *,
    vendor: Path | None,
    http_base: str,
    autostart: bool,
) -> None:
    """Ensure HTTP canvas responds on ``http_base``; optionally build + spawn Node."""
    global _canvas_proc, _we_started_canvas

    base = http_base.rstrip("/")
    host, port = _parse_http_base(base)

    data = await _health_payload(base)
    if data and data.get("status") == "healthy":
        log.debug("Excalidraw canvas HTTP already healthy at %s", base)
        await _ensure_playwright_ws_client(base=base, vendor=vendor)
        return

    if not autostart:
        raise RuntimeError(
            f"Excalidraw canvas is not reachable at {base}. "
            "Enable EXCALIDRAW_CANVAS_AUTOSTART or start it manually "
            "(see vendor/mcp_excalidraw: npm run canvas)."
        )

    root = _resolve_vendor(vendor)
    if not root.is_dir():
        raise RuntimeError(
            f"mcp_excalidraw checkout missing at {root}. Clone with: "
            "git clone --depth 1 https://github.com/yctimlin/mcp_excalidraw.git "
            f"into {root.parent}"
        )

    await ensure_vendor_build(root)

    if _canvas_proc is not None and _canvas_proc.poll() is None:
        retry_payload = await _health_payload(base)
        if retry_payload and retry_payload.get("status") == "healthy":
            await _ensure_playwright_ws_client(base=base, vendor=vendor)
            return
        await _stop_canvas_sync()

    node = _node_cmd()
    server_js = root / "dist" / "server.js"
    if not server_js.is_file():
        raise RuntimeError(f"Missing {server_js} — npm run build incomplete.")

    env = {**os.environ, "HOST": host, "PORT": str(port)}
    stderr_path = (
        Path(tempfile.gettempdir())
        / f"ladder-exc-canvas-{os.getpid()}-{port}.stderr.log"
    )
    stderr_path.unlink(missing_ok=True)

    kw: dict[str, Any] = {"cwd": str(root), "env": env, "stdout": subprocess.DEVNULL}
    stderr_f = None
    try:
        stderr_f = open(stderr_path, "wb")  # noqa: SIM115
        kw["stderr"] = stderr_f
    except OSError as e:
        log.warning("could not open excalidraw stderr log %s: %s", stderr_path, e)
        kw["stderr"] = subprocess.DEVNULL

    if sys.platform == "win32":
        kw["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)

    def _spawn_canvas() -> subprocess.Popen[bytes]:
        return subprocess.Popen([node, str(server_js)], **kw)

    log.info("Starting Excalidraw canvas server: %s %s", node, server_js)
    try:
        _canvas_proc = await asyncio.to_thread(_spawn_canvas)
    finally:
        if stderr_f is not None:
            try:
                stderr_f.close()
            except OSError:
                pass

    _we_started_canvas = True

    loop = asyncio.get_running_loop()
    deadline = loop.time() + float(settings.EXCALIDRAW_CANVAS_HEALTH_WAIT_SECONDS)

    while loop.time() < deadline:
        if _canvas_proc.poll() is not None:
            code = _canvas_proc.poll()
            tail = _stderr_tail(stderr_path)
            await _stop_canvas_sync()
            hint = ""
            if "already listening" in tail or "EADDRINUSE" in tail.lower():
                pu = urlparse(base)
                alt_host = pu.hostname or "127.0.0.1"
                alt_url = pu._replace(netloc=f"{alt_host}:3099").geturl()
                hint = (
                    " Another listener may occupy this loopback port — "
                    f"stop it or set EXCALIDRAW_HTTP_URL={alt_url} "
                    "(duplicate canvas servers often refuse to bind)."
                )
            raise RuntimeError(
                "Excalidraw canvas process exited before /health succeeded "
                f"(exit_code={code}). Stderr tail: {tail!r}.{hint}"
            )

        hp = await _health_payload(base)
        if hp and hp.get("status") == "healthy":
            log.info(
                "Excalidraw canvas listening on port %s (%s websocket clients)",
                port,
                hp.get("websocket_clients", "?"),
            )
            try:
                stderr_path.unlink(missing_ok=True)
            except OSError:
                pass
            await _ensure_playwright_ws_client(base=base, vendor=vendor)
            return

        await asyncio.sleep(0.35)

    await _stop_canvas_sync()
    tail = _stderr_tail(stderr_path)
    raise RuntimeError(
        f"Excalidraw canvas failed to accept /health on {base} within "
        f"{settings.EXCALIDRAW_CANVAS_HEALTH_WAIT_SECONDS}s. Stderr tail: {tail!r}."
    )


async def shutdown_managed_children() -> None:
    """Terminate canvas/headless subprocesses started by this module."""
    await _stop_headless_sync()
    await _stop_canvas_sync()
