"""Managed local Excalidraw canvas stack (``yctimlin/mcp_excalidraw``).

Spawns ``dist/server.js`` on loopback — the same bundle the MCP server expects
behind ``EXPRESS_SERVER_URL``. First boot may run ``npm ci`` + ``npm run build``
inside the vendor checkout when artefacts are missing; requires Node 18+ and npm.

See: ``https://github.com/yctimlin/mcp_excalidraw`` (peer to ``robonuggets/excalidraw-skill``).
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
from urllib.parse import urlparse

import httpx

from app.config import settings

log = logging.getLogger(__name__)


def _stderr_tail(path: Path, limit: int = 6000) -> str:
    try:
        data = path.read_bytes()
        return data[-limit:].decode(errors="replace")
    except OSError:
        return ""


_proc: subprocess.Popen[bytes] | None = None
_build_lock = asyncio.Lock()


def default_vendor_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent / "vendor" / "mcp_excalidraw"


def _npm_cmd(*args: str) -> list[str]:
    npm = shutil.which("npm.cmd") if sys.platform == "win32" else shutil.which("npm")
    if not npm:
        raise RuntimeError(
            "npm is required to build the Excalidraw canvas. Install Node.js 18+ and "
            "ensure `npm` is on PATH."
        )
    # On Windows shutil.which returns full path often ending in .cmd
    return [npm, *args]


def _node_cmd() -> str:
    exe = shutil.which("node") or shutil.which("node.exe")
    if not exe:
        raise RuntimeError(
            "`node` is required to run the Excalidraw canvas. Install Node.js 18+ "
            "and ensure `node` is on PATH."
        )
    return exe


def _build_complete(vendor: Path) -> bool:
    idx = vendor / "dist" / "frontend" / "index.html"
    srv = vendor / "dist" / "server.js"
    return idx.is_file() and srv.is_file()


async def ensure_vendor_build(vendor: Path) -> None:
    """Ensure ``npm ci`` / ``npm run build`` succeeded at least once."""
    async with _build_lock:
        if _build_complete(vendor):
            return
        loop = asyncio.get_running_loop()

        def _run() -> None:
            subprocess.run(_npm_cmd("ci"), cwd=str(vendor), check=True)
            subprocess.run(_npm_cmd("run", "build"), cwd=str(vendor), check=True)

        await loop.run_in_executor(None, _run)
        if not _build_complete(vendor):
            raise RuntimeError(
                f"Expected dist bundle under {vendor} after npm build — check Node/npm logs."
            )


async def canvas_health(http_base: str) -> tuple[bool, dict | None]:
    url = http_base.rstrip("/") + "/health"
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(3.0)) as c:
            r = await c.get(url)
        if r.status_code != 200:
            return False, None
        return True, r.json()
    except Exception:
        return False, None


async def stop_canvas_process() -> None:
    global _proc
    if _proc is None:
        return
    proc = _proc
    _proc = None
    try:
        proc.terminate()
        await asyncio.wait_for(asyncio.to_thread(proc.wait), timeout=8.0)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


async def ensure_canvas_running(
    *,
    vendor: Path | None,
    http_base: str,
    autostart: bool = True,
) -> None:
    """If nothing listens on ``http_base`` /health and ``autostart``, spawn Node."""
    parsed = urlparse(http_base)
    host = parsed.hostname or "127.0.0.1"
    port = int(parsed.port or 3000)

    ok, _ = await canvas_health(http_base)
    if ok:
        return
    if not autostart:
        raise RuntimeError(
            f"Excalidraw canvas is not reachable at {http_base}. "
            "Enable EXCALIDRAW_CANVAS_AUTOSTART or start it manually "
            "(see vendor/mcp_excalidraw: PORT=3000 npm run canvas)."
        )

    v = vendor or default_vendor_root()
    if not v.is_dir():
        raise RuntimeError(
            f"mcp_excalidraw checkout missing at {v}. Clone with: "
            "git clone --depth 1 https://github.com/yctimlin/mcp_excalidraw.git "
            f"into backend/vendor/mcp_excalidraw"
        )

    await ensure_vendor_build(v)

    global _proc
    if _proc is not None and _proc.poll() is None:
        ok2, _ = await canvas_health(http_base)
        if ok2:
            return
        await stop_canvas_process()

    node = _node_cmd()
    server_js = v / "dist" / "server.js"
    if not server_js.is_file():
        raise RuntimeError(f"Missing {server_js} — npm run build incomplete.")

    env = {**os.environ, "HOST": host, "PORT": str(port)}
    stderr_path = Path(tempfile.gettempdir()) / f"ladder-exc-canvas-{os.getpid()}-{port}.stderr.log"
    stderr_path.unlink(missing_ok=True)

    kw: dict[str, object] = {
        "cwd": str(v),
        "env": env,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    stderr_f = None
    try:
        stderr_f = open(stderr_path, "wb")  # noqa: SIM115 — closed after Popen
        kw["stderr"] = stderr_f
    except OSError as e:
        log.warning("could not open excalidraw stderr log %s: %s", stderr_path, e)

    if sys.platform == "win32":
        kw["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)

    def _spawn() -> subprocess.Popen[bytes]:
        return subprocess.Popen([node, str(server_js)], **kw)  # type: ignore[arg-type]

    try:
        _proc = await asyncio.to_thread(_spawn)
    finally:
        if stderr_f is not None:
            try:
                stderr_f.close()
            except OSError:
                pass

    loop = asyncio.get_running_loop()
    deadline = loop.time() + float(settings.EXCALIDRAW_CANVAS_HEALTH_WAIT_SECONDS)

    while loop.time() < deadline:
        code = _proc.poll()
        if code is not None:
            tail = _stderr_tail(stderr_path)
            await stop_canvas_process()
            hint = ""
            if "already listening" in tail or "EADDRINUSE" in tail.lower():
                pu = urlparse(http_base)
                alt_host = pu.hostname or "127.0.0.1"
                alt_url = pu._replace(netloc=f"{alt_host}:3099").geturl()
                hint = (
                    " Another listener may occupy this loopback port — "
                    f"stop it or set EXCALIDRAW_HTTP_URL={alt_url} "
                    "(mcp_excalidraw refuses to start duplicate canvas servers)."
                )
            raise RuntimeError(
                "Excalidraw canvas process exited before /health succeeded "
                f"(exit_code={code}). Stderr tail: {tail!r}.{hint}"
            )

        ok_poll, meta = await canvas_health(http_base)
        if ok_poll:
            log.info(
                "excalidraw canvas listening on port %s (%s websocket clients)",
                port,
                (meta or {}).get("websocket_clients", "?"),
            )
            try:
                stderr_path.unlink(missing_ok=True)
            except OSError:
                pass
            return
        await asyncio.sleep(0.35)

    await stop_canvas_process()
    tail = _stderr_tail(stderr_path)
    raise RuntimeError(
        f"Excalidraw canvas failed to accept /health on {http_base} within "
        f"{settings.EXCALIDRAW_CANVAS_HEALTH_WAIT_SECONDS}s. Stderr tail: {tail!r}. "
        "If this is WSL on /mnt/d/, pre-build once: "
        f"cd {v} && npm ci && npm run build"
    )