"""Manage the vendored ``mcp_Research_agent`` server and provide a JSON-RPC client."""

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

_agent_proc: subprocess.Popen[bytes] | None = None
_we_started_agent = False
_agent_lock = asyncio.Lock()


def _resolve_vendor() -> Path:
    raw = settings.MCP_RESEARCH_AGENT_VENDOR_ROOT.strip()
    return Path(raw).resolve()


def _uvicorn_cmd() -> list[str]:
    # Try to use uv if available, otherwise fallback to python -m uvicorn
    # The vendor directory has a pyproject.toml, so we can run it with uv run
    uv = shutil.which("uv")
    if uv:
        return [uv, "run", "uvicorn"]
    python = sys.executable
    return [python, "-m", "uvicorn"]


def _research_agent_env() -> dict[str, str]:
    """Build subprocess env with keys loaded from the backend settings object.

    Pydantic reads backend/.env into ``settings`` but does not export those
    values into os.environ. The vendored research agent loads its own .env from
    its cwd, so deployed installs without vendor/mcp_Research_agent/.env still
    need the backend-provided provider keys here.
    """
    env = os.environ.copy()

    mappings = {
        "ANTHROPIC_API_KEY": settings.ANTHROPIC_API_KEY,
        "OPENAI_API_KEY": settings.OPENAI_API_KEY,
        "GOOGLE_API_KEY": settings.GOOGLE_API_KEY,
        "EXA_API_KEY": settings.EXA_API_KEY,
        "SUPABASE_URL": settings.SUPABASE_URL,
        "SUPABASE_SERVICE_ROLE_KEY": settings.SUPABASE_SERVICE_ROLE_KEY,
        # Backend config historically used SCRAPECREATORS_API_KEY; the
        # research agent expects SCRAPE_CREATORS_API_KEY.
        "SCRAPE_CREATORS_API_KEY": settings.SCRAPECREATORS_API_KEY,
    }

    for key, value in mappings.items():
        if value:
            env[key] = value

    return env


def _stderr_tail(path: Path, limit: int = 6000) -> str:
    try:
        data = path.read_bytes()
        return data[-limit:].decode(errors="replace")
    except OSError:
        return ""


def _parse_http_base(http_base: str) -> tuple[str, int]:
    u = urlparse(http_base if "://" in http_base else f"http://{http_base}")
    host = u.hostname or "127.0.0.1"
    port = u.port or 8000
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


async def _stop_agent_sync() -> None:
    global _agent_proc, _we_started_agent
    if _agent_proc is None:
        return
    proc = _agent_proc
    _agent_proc = None
    try:
        proc.terminate()
        await asyncio.wait_for(asyncio.to_thread(proc.wait), timeout=8.0)
    except TimeoutError:
        proc.kill()
    except ProcessLookupError:
        pass
    _we_started_agent = False


async def ensure_mcp_research_running() -> None:
    """Ensure HTTP MCP agent responds; optionally spawn uvicorn."""
    global _agent_proc, _we_started_agent

    base = settings.MCP_RESEARCH_AGENT_URL.rstrip("/")
    host, port = _parse_http_base(base)

    data = await _health_payload(base)
    if data and data.get("status") in ("healthy", "UP"):
        log.debug("MCP Research Agent HTTP already healthy at %s", base)
        return

    if not settings.MCP_RESEARCH_AGENT_AUTOSTART:
        raise RuntimeError(
            f"MCP Research Agent is not reachable at {base}. "
            "Enable MCP_RESEARCH_AGENT_AUTOSTART or start it manually."
        )

    root = _resolve_vendor()
    if not root.is_dir():
        raise RuntimeError(f"MCP Research Agent checkout missing at {root}.")

    async with _agent_lock:
        if _agent_proc is not None and _agent_proc.poll() is None:
            retry_payload = await _health_payload(base)
            if retry_payload and retry_payload.get("status") in ("healthy", "UP"):
                return
            await _stop_agent_sync()

        cmd = _uvicorn_cmd() + ["research_agent.main:app", "--host", host, "--port", str(port)]
        
        env = _research_agent_env()

        stderr_path = (
            Path(tempfile.gettempdir())
            / f"ladder-mcp-research-{os.getpid()}-{port}.stderr.log"
        )
        stderr_path.unlink(missing_ok=True)

        kw: dict[str, Any] = {"cwd": str(root), "env": env, "stdout": subprocess.DEVNULL}
        stderr_f = None
        try:
            stderr_f = open(stderr_path, "wb")
            kw["stderr"] = stderr_f
        except OSError as e:
            log.warning("could not open MCP research stderr log %s: %s", stderr_path, e)
            kw["stderr"] = subprocess.DEVNULL

        if sys.platform == "win32":
            kw["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)

        def _spawn_agent() -> subprocess.Popen[bytes]:
            return subprocess.Popen(cmd, **kw)

        log.info("Starting MCP Research Agent: %s", " ".join(cmd))
        try:
            _agent_proc = await asyncio.to_thread(_spawn_agent)
        finally:
            if stderr_f is not None:
                try:
                    stderr_f.close()
                except OSError:
                    pass

        _we_started_agent = True

        loop = asyncio.get_running_loop()
        deadline = loop.time() + float(settings.MCP_RESEARCH_AGENT_HEALTH_WAIT_SECONDS)

        while loop.time() < deadline:
            if _agent_proc.poll() is not None:
                code = _agent_proc.poll()
                tail = _stderr_tail(stderr_path)
                await _stop_agent_sync()
                raise RuntimeError(
                    "MCP Research Agent process exited before /health succeeded "
                    f"(exit_code={code}). Stderr tail: {tail!r}."
                )

            hp = await _health_payload(base)
            if hp and hp.get("status") in ("healthy", "UP"):
                log.info("MCP Research Agent listening on port %s", port)
                try:
                    stderr_path.unlink(missing_ok=True)
                except OSError:
                    pass
                return

            await asyncio.sleep(0.35)

        await _stop_agent_sync()
        tail = _stderr_tail(stderr_path)
        raise RuntimeError(
            f"MCP Research Agent failed to accept /health on {base} within "
            f"{settings.MCP_RESEARCH_AGENT_HEALTH_WAIT_SECONDS}s. Stderr tail: {tail!r}."
        )


async def shutdown_mcp_research() -> None:
    """Terminate MCP agent subprocess started by this module."""
    await _stop_agent_sync()


async def call_mcp_research(
    query: str,
    context: dict[str, Any],
    cost_ceiling: float | None = None,
) -> dict[str, Any]:
    """Execute research via the MCP JSON-RPC endpoint.

    Returns the parsed ResearchResult dict.
    """
    await ensure_mcp_research_running()
    
    url = f"{settings.MCP_RESEARCH_AGENT_URL.rstrip('/')}/mcp"
    
    payload = {
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {
            "name": "run_research",
            "arguments": {
                "query": query,
                "context": context,
                "config": {
                    "cost_ceiling": cost_ceiling or settings.MCP_RESEARCH_COST_CEILING,
                    "timeout_seconds": settings.MCP_RESEARCH_TIMEOUT_SECONDS,
                }
            }
        },
        "id": 1
    }
    
    timeout = httpx.Timeout(settings.MCP_RESEARCH_TIMEOUT_SECONDS + 10.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            
            if "error" in data:
                raise RuntimeError(f"MCP Research Error: {data['error']}")
                
            # The MCP tool result typically returns a JSON string in content[0].text
            # or structured data. Based on MCP specs, let's unpack it.
            result_obj = data.get("result", {})
            if result_obj.get("isError"):
                content = result_obj.get("content", [{}])[0].get("text", "Unknown error")
                raise RuntimeError(f"MCP Tool Error: {content}")
                
            content = result_obj.get("content", [{}])[0]
            if "text" in content:
                import json
                try:
                    parsed = json.loads(content["text"])
                    return parsed.get("data", parsed)
                except json.JSONDecodeError:
                    return {"raw_text": content["text"]}
            
            return result_obj
            
        except httpx.ReadTimeout:
            raise RuntimeError(f"MCP Research Agent timed out after {settings.MCP_RESEARCH_TIMEOUT_SECONDS}s")
        except Exception as e:
            raise RuntimeError(f"Failed to call MCP Research Agent: {e}")


async def stream_mcp_research(
    query: str,
    context: dict[str, Any],
    cost_ceiling: float | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Execute research async and yield intermediate events, then return final result as the last yielded item."""
    await ensure_mcp_research_running()
    
    url = f"{settings.MCP_RESEARCH_AGENT_URL.rstrip('/')}/mcp"
    
    payload = {
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {
            "name": "run_research",
            "arguments": {
                "query": query,
                "context": context,
                "config": {
                    "cost_ceiling": cost_ceiling or settings.MCP_RESEARCH_COST_CEILING,
                    "timeout_seconds": settings.MCP_RESEARCH_TIMEOUT_SECONDS,
                },
                "async": True
            }
        },
        "id": 1
    }
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        data = resp.json()
        
        result_obj = data.get("result", {})
        if result_obj.get("isError"):
            content = result_obj.get("content", [{}])[0].get("text", "Unknown error")
            raise RuntimeError(f"MCP Tool Error: {content}")
            
        content_text = result_obj.get("content", [{}])[0].get("text", "{}")
        import json
        try:
            parsed = json.loads(content_text)
            run_data = parsed.get("data", {})
        except json.JSONDecodeError:
            raise RuntimeError(f"Invalid JSON from MCP: {content_text}")
            
        run_id = run_data.get("run_id")
        ws_url = run_data.get("websocket_url")
        
        if not run_id:
            raise RuntimeError(f"MCP returned no run_id: {run_data}")
            
        # Connect to websocket for streaming events
        if ws_url:
            import websockets
            import websockets.exceptions
            full_ws_url = f"{settings.MCP_RESEARCH_AGENT_URL.replace('http://', 'ws://').replace('https://', 'wss://').rstrip('/')}{ws_url}"
            try:
                async with websockets.connect(full_ws_url) as ws:
                    while True:
                        try:
                            msg = await asyncio.wait_for(ws.recv(), timeout=2.0)
                            msg_data = json.loads(msg)
                            yield {"type": "stream_event", "event": msg_data}
                        except asyncio.TimeoutError:
                            # Poll to check if it's done
                            res = await client.post(url, json={
                                "jsonrpc": "2.0",
                                "method": "tools/call",
                                "params": {"name": "get_research_result", "arguments": {"run_id": run_id}},
                                "id": 2
                            })
                            r_data = res.json()
                            if r_data.get("error"):
                                continue
                            r_content = r_data.get("result", {}).get("content", [{}])[0].get("text", "{}")
                            r_parsed = json.loads(r_content).get("data", {})
                            if r_parsed.get("status") in ("complete", "failed", "error", "rejected"):
                                yield {"type": "final_result", "result": r_parsed}
                                break
                        except websockets.exceptions.ConnectionClosed:
                            break
            except Exception as e:
                log.warning(f"Failed to stream via websocket: {e}")
        
        # If WS failed or closed before finishing, poll until complete
        while True:
            res = await client.post(url, json={
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {"name": "get_research_result", "arguments": {"run_id": run_id}},
                "id": 3
            })
            r_data = res.json()
            r_content = r_data.get("result", {}).get("content", [{}])[0].get("text", "{}")
            r_parsed = json.loads(r_content).get("data", {})
            if r_parsed.get("status") in ("complete", "failed", "error", "rejected"):
                yield {"type": "final_result", "result": r_parsed}
                break
            await asyncio.sleep(2.0)
