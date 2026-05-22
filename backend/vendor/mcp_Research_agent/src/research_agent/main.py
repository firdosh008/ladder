"""FastAPI server — REST + WebSocket endpoints for the research agent.
Connects to the frontend UI via real-time event streaming."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid
from dataclasses import asdict
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from research_agent.config import settings
from research_agent.models import ResearchConfig, ResearchInput, ResearchResult
from research_agent.graph.orchestrator import run_research
from research_agent.ops import configure_langsmith, cost_summary, maybe_send_cost_alert
from research_agent.rollout import compare_shadow_outputs, run_legacy_shadow, unified_enabled
from research_agent.storage import get_research_result as get_stored_research_result
from research_agent.storage import init_storage, save_research_result

# ──────────────────────────────────────────────
# Logging
# ──────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


class RedactSecretsFilter(logging.Filter):
    """Redact provider credentials that appear in logged request URLs."""

    _pattern = re.compile(r"([?&](?:key|token|api_key|apiKey|password)=)[^&\s\"]+", re.IGNORECASE)

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        redacted = self._pattern.sub(r"\1[REDACTED]", message)
        if redacted != message:
            record.msg = redacted
            record.args = ()
        return True


_redact_filter = RedactSecretsFilter()
logging.getLogger().addFilter(_redact_filter)
logging.getLogger("httpx").addFilter(_redact_filter)
for handler in logging.getLogger().handlers:
    handler.addFilter(_redact_filter)

# ──────────────────────────────────────────────
# App
# ──────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Startup and shutdown events."""
    configure_langsmith()
    await init_storage()
    yield


app = FastAPI(
    title="Standalone Research Agent",
    description="Multi-platform research engine with REST, UI, and direct JSON-RPC MCP tools",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS for local dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve the UI
app.mount("/static", StaticFiles(directory="ui"), name="static")

# In-memory run storage (swap for Postgres in production)
runs: dict[str, ResearchResult] = {}
active_websockets: dict[str, list[WebSocket]] = {}


@app.middleware("http")
async def log_mcp_requests(req: Request, call_next):
    """Log MCP requests when they arrive, not only after the long tool call returns."""
    if req.url.path == "/mcp":
        logger.info(f"[MCP] HTTP request received: {req.method} {req.url.path}")
    response = await call_next(req)
    if req.url.path == "/mcp":
        logger.info(f"[MCP] HTTP response sent: {response.status_code}")
    return response





# ──────────────────────────────────────────────
# Request / Response models
# ──────────────────────────────────────────────

class ResearchRequest(BaseModel):
    query: str
    context: dict[str, Any] = Field(default_factory=dict)
    config: dict[str, Any] = Field(default_factory=dict)
    output_mode: str | None = None
    input_type: str = "freeform"
    user_id: str = "default"
    product: str | None = None
    cost_ceiling: float = 3.0
    timeout_seconds: int = 300
    lens_preferences: list[str] | None = None
    skip_platforms: list[str] = Field(default_factory=list)

class RunResponse(BaseModel):
    run_id: str
    status: str


def _serialize(obj: Any) -> Any:
    """Recursively serialize dataclass/dict for JSON."""
    if hasattr(obj, '__dataclass_fields__'):
        return {k: _serialize(v) for k, v in asdict(obj).items()}
    elif isinstance(obj, list):
        return [_serialize(i) for i in obj]
    elif isinstance(obj, dict):
        return {k: _serialize(v) for k, v in obj.items()}
    return obj


def _effective_output_mode(req: ResearchRequest) -> str:
    return req.output_mode or req.product or "research_report"


def _config_from_request(req: ResearchRequest) -> ResearchConfig:
    raw = req.config or {}
    return ResearchConfig(
        cost_ceiling=float(raw.get("cost_ceiling", req.cost_ceiling)),
        timeout_seconds=int(raw.get("timeout_seconds", req.timeout_seconds)),
        lens_preferences=raw.get("lens_preferences", req.lens_preferences),
        skip_platforms=list(raw.get("skip_platforms", req.skip_platforms) or []),
    )


def _config_from_args(args: dict[str, Any]) -> ResearchConfig:
    raw = args.get("config") or {}
    return ResearchConfig(
        cost_ceiling=float(raw.get("cost_ceiling", args.get("cost_ceiling", 3.0))),
        timeout_seconds=int(raw.get("timeout_seconds", args.get("timeout_seconds", 300))),
        lens_preferences=raw.get("lens_preferences", args.get("lens_preferences")),
        skip_platforms=list(raw.get("skip_platforms", args.get("skip_platforms", [])) or []),
    )


def _mcp_success(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "content": [
            {
                "type": "text",
                "text": json.dumps({"success": True, **payload, "timestamp": _now_iso()}, indent=2),
            }
        ]
    }


def _mcp_failure(message: str, code: str = "TOOL_ERROR") -> dict[str, Any]:
    return {
        "content": [
            {
                "type": "text",
                "text": json.dumps({
                    "success": False,
                    "error": message,
                    "errorCode": code,
                    "timestamp": _now_iso(),
                }, indent=2),
            }
        ]
    }


def _jsonrpc_result(request_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _jsonrpc_error(request_id: Any, code: int, message: str, data: Any = None) -> dict[str, Any]:
    error = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return {"jsonrpc": "2.0", "id": request_id, "error": error}


def _now_iso() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat()


MCP_TOOLS: list[dict[str, Any]] = [
    {
        "name": "run_research",
        "description": "Run the standalone research pipeline for a topic and return the completed research report.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Research topic, URL, or freeform brief."},
                "context": {
                    "type": "object",
                    "description": "Optional caller-provided project, audience, past-topic, voice, or niche context.",
                    "additionalProperties": True,
                },
                "config": {
                    "type": "object",
                    "description": "Optional per-run controls such as cost_ceiling, timeout_seconds, skip_platforms, and lens_preferences.",
                    "additionalProperties": True,
                },
                "output_mode": {
                    "type": "string",
                    "description": "Output adapter to use. research_report is standalone; ladderflow and ladderbrief are legacy adapters.",
                    "enum": ["research_report", "ladderflow", "ladderbrief"],
                    "default": "research_report",
                },
                "input_type": {
                    "type": "string",
                    "enum": ["keywords", "youtube_url", "newsletter_url", "freeform"],
                    "default": "freeform",
                },
                "user_id": {"type": "string", "default": "default"},
                "run_id": {"type": "string", "description": "Optional caller-supplied run identifier."},
                "async": {
                    "type": "boolean",
                    "description": "When true, start the run in the background and return run_id immediately for WebSocket or get_research_result polling.",
                    "default": False,
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_research_result",
        "description": "Fetch a completed research result by run_id.",
        "inputSchema": {
            "type": "object",
            "properties": {"run_id": {"type": "string", "description": "Research run identifier."}},
            "required": ["run_id"],
        },
    },
    {
        "name": "list_sources",
        "description": "List the source references collected for a completed research run.",
        "inputSchema": {
            "type": "object",
            "properties": {"run_id": {"type": "string", "description": "Research run identifier."}},
            "required": ["run_id"],
        },
    },
    {
        "name": "run_eval",
        "description": "Run the local evaluation harness against a JSON dataset.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "dataset_path": {
                    "type": "string",
                    "description": "Path to eval dataset JSON.",
                    "default": "eval_dataset.example.json",
                },
                "subset": {
                    "type": "integer",
                    "description": "Optional number of cases to run from the start of the dataset.",
                    "minimum": 1,
                },
            },
        },
    },
    {
        "name": "export_research_json",
        "description": "Export the whole research, including all raw details, comments, and videos, to a local JSON file.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "run_id": {"type": "string", "description": "Research run identifier."},
                "output_path": {"type": "string", "description": "Optional local file path to save the JSON. Defaults to exports/<run_id>.json"}
            },
            "required": ["run_id"],
        },
    },
]


# ──────────────────────────────────────────────
# REST Endpoints
# ──────────────────────────────────────────────

@app.get("/")
async def root():
    """Serve the UI."""
    return FileResponse("ui/index.html")


@app.post("/api/research", response_model=RunResponse)
async def start_research_endpoint(req: ResearchRequest):
    """Start a new research run. Returns immediately with run_id.
    Connect to the WebSocket at /ws/research/{run_id} for real-time updates."""
    output_mode = _effective_output_mode(req)
    if output_mode in {"ladderflow", "ladderbrief"} and not unified_enabled(output_mode):
        raise HTTPException(status_code=503, detail=f"Research adapter disabled for {output_mode}")

    run_id = str(uuid.uuid4())

    # Start the research in the background
    asyncio.create_task(_run_research_background(run_id, req))

    return RunResponse(run_id=run_id, status="started")


@app.get("/api/research/{run_id}")
async def get_research_result(run_id: str):
    """Get the result of a completed research run."""
    stored = await get_stored_research_result(run_id)
    if stored:
        return stored

    if run_id not in runs:
        raise HTTPException(status_code=404, detail="Run not found")

    result = runs[run_id]
    return _serialize(result)


@app.get("/api/research/{run_id}/export")
async def export_research_endpoint(run_id: str):
    """Export the full research result including raw data."""
    stored = await get_stored_research_result(run_id)
    result = stored or runs.get(run_id)
    if not result:
        raise HTTPException(status_code=404, detail="Run not found")
    
    from fastapi.responses import JSONResponse
    return JSONResponse(content=_serialize(result))


@app.get("/api/health")
async def health():
    return {"status": "healthy", "version": "1.0.0"}


@app.get("/health")
async def mcp_health():
    return {
        "status": "UP",
        "server": "standalone-research-agent-mcp",
        "version": "1.0.0",
        "tools": {"total": len(MCP_TOOLS), "names": [tool["name"] for tool in MCP_TOOLS]},
        "timestamp": _now_iso(),
    }


@app.get("/api/ops/costs")
async def get_cost_summary():
    return await cost_summary()


@app.post("/mcp")
async def mcp_endpoint(payload: dict[str, Any]):
    """Direct JSON-RPC 2.0 MCP endpoint. No MCP SDK or WebSocket transport required."""
    method = payload.get("method")
    request_id = payload.get("id")
    logger.info(f"[MCP] JSON-RPC method={method} id={request_id}")

    if method == "initialize":
        return _jsonrpc_result(request_id, {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}, "logging": {}},
            "serverInfo": {"name": "standalone-research-agent-mcp", "version": "1.0.0"},
        })

    if method == "notifications/initialized":
        return _jsonrpc_result(request_id, {})

    if method == "tools/list":
        return _jsonrpc_result(request_id, {"tools": MCP_TOOLS})

    if method == "tools/call":
        params = payload.get("params") or {}
        tool_name = params.get("name")
        args = params.get("arguments") or {}
        try:
            result = await _call_mcp_tool(tool_name, args)
            return _jsonrpc_result(request_id, result)
        except Exception as e:
            logger.error(f"MCP tool call failed for {tool_name}: {e}", exc_info=True)
            return _jsonrpc_error(request_id, -32603, str(e))

    return _jsonrpc_error(request_id, -32601, f"Unsupported MCP method: {method}")


async def _call_mcp_tool(tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
    logger.info(f"[MCP] tools/call name={tool_name}")
    if tool_name == "run_research":
        return await _mcp_run_research(args)
    if tool_name == "get_research_result":
        return await _mcp_get_research_result(args)
    if tool_name == "list_sources":
        return await _mcp_list_sources(args)
    if tool_name == "run_eval":
        return await _mcp_run_eval(args)
    if tool_name == "export_research_json":
        return await _mcp_export_research_json(args)
    return _mcp_failure(f"Unknown tool: {tool_name}", "UNKNOWN_TOOL")


async def _mcp_run_research(args: dict[str, Any]) -> dict[str, Any]:
    query = str(args.get("query") or "").strip()
    if not query:
        return _mcp_failure("query is required", "VALIDATION_ERROR")

    output_mode = args.get("output_mode") or "research_report"
    user_id = args.get("user_id") or "default"
    run_id = args.get("run_id") or str(uuid.uuid4())
    context = args.get("context") or {}
    run_config = _config_from_args(args)
    logger.info(
        f"[MCP run {run_id}] START query={query!r} output_mode={output_mode} "
        f"async={args.get('async') is True} skip_platforms={run_config.skip_platforms}"
    )

    if args.get("async") is True:
        req = ResearchRequest(
            query=query,
            context=context,
            config=args.get("config") or {},
            output_mode=output_mode,
            input_type=args.get("input_type") or "freeform",
            user_id=user_id,
            lens_preferences=args.get("lens_preferences"),
        )
        runs[run_id] = ResearchResult(run_id=run_id, status="running")
        asyncio.create_task(_run_research_background(run_id, req))
        logger.info(f"[MCP run {run_id}] BACKGROUND task created")
        return _mcp_success({
            "data": {
                "run_id": run_id,
                "status": "started",
                "websocket_url": f"/ws/research/{run_id}",
                "result_url": f"/api/research/{run_id}",
            }
        })

    async def event_callback(event: dict):
        logger.info(
            f"[MCP run {run_id}] {event.get('event', '')} "
            f"layer={event.get('layer', '')} agent={event.get('agent', '')} "
            f"message={event.get('message', '')}"
        )

    result = await run_research(
        input=ResearchInput(
            query=query,
            input_type=args.get("input_type") or "freeform",
            user_id=user_id,
            context=context,
            output_mode=output_mode,
            product=output_mode,
            lens_preferences=args.get("lens_preferences"),
        ),
        config=run_config,
        context=context,
        run_id=run_id,
        event_callback=event_callback,
    )
    runs[run_id] = result
    await save_research_result(result, query=query, user_id=user_id, product=output_mode)
    await maybe_send_cost_alert(result)
    logger.info(
        f"[MCP run {run_id}] COMPLETE status={result.status} "
        f"sources={len(result.sources)} cost=${result.cost_breakdown.total:.2f} "
        f"duration={result.cost_breakdown.duration_seconds}s"
    )
    return _mcp_success({"data": _serialize(result)})


async def _mcp_get_research_result(args: dict[str, Any]) -> dict[str, Any]:
    run_id = str(args.get("run_id") or "").strip()
    if not run_id:
        return _mcp_failure("run_id is required", "VALIDATION_ERROR")

    stored = await get_stored_research_result(run_id)
    if stored:
        return _mcp_success({"data": stored})
    if run_id not in runs:
        return _mcp_failure("Run not found", "NOT_FOUND")
    return _mcp_success({"data": _serialize(runs[run_id])})


async def _mcp_export_research_json(args: dict[str, Any]) -> dict[str, Any]:
    run_id = str(args.get("run_id") or "").strip()
    if not run_id:
        return _mcp_failure("run_id is required", "VALIDATION_ERROR")
    
    stored = await get_stored_research_result(run_id)
    result = stored or runs.get(run_id)
    if not result:
        return _mcp_failure("Run not found", "NOT_FOUND")
        
    output_path = args.get("output_path")
    if not output_path:
        import os
        os.makedirs("exports", exist_ok=True)
        output_path = f"exports/{run_id}.json"
        
    try:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(_serialize(result), f, indent=2)
        return _mcp_success({"data": {"message": f"Successfully exported to {output_path}", "path": output_path}})
    except Exception as e:
        return _mcp_failure(f"Failed to export: {str(e)}", "EXPORT_ERROR")


async def _mcp_list_sources(args: dict[str, Any]) -> dict[str, Any]:
    result_payload = await _mcp_get_research_result(args)
    text = result_payload["content"][0]["text"]
    payload = json.loads(text)
    if not payload.get("success"):
        return result_payload
    result = payload.get("data") or {}
    return _mcp_success({"data": {"run_id": args.get("run_id"), "sources": result.get("sources", [])}})


async def _mcp_run_eval(args: dict[str, Any]) -> dict[str, Any]:
    from research_agent.eval import run_eval_dataset

    dataset_path = args.get("dataset_path") or "eval_dataset.example.json"
    subset = args.get("subset")
    result = await run_eval_dataset(dataset_path, subset=int(subset) if subset else None)
    return _mcp_success({"data": result})


# ──────────────────────────────────────────────
# WebSocket — real-time event streaming
# ──────────────────────────────────────────────

@app.websocket("/ws/research/{run_id}")
async def research_websocket(websocket: WebSocket, run_id: str):
    """WebSocket endpoint for streaming real-time pipeline events to the UI."""
    await websocket.accept()
    logger.info(f"WebSocket connected for run {run_id}")

    # Register this websocket
    if run_id not in active_websockets:
        active_websockets[run_id] = []
    active_websockets[run_id].append(websocket)

    try:
        # Keep connection alive until client disconnects
        while True:
            # Listen for any client messages (e.g., cancel)
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=300)
                if data == "cancel":
                    logger.info(f"Run {run_id} cancelled by client")
                    break
            except asyncio.TimeoutError:
                # Send ping to keep alive
                await websocket.send_json({"event": "ping"})
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for run {run_id}")
    finally:
        if run_id in active_websockets:
            active_websockets[run_id].remove(websocket)
            if not active_websockets[run_id]:
                del active_websockets[run_id]


async def _broadcast_event(run_id: str, event: dict):
    """Send an event to all connected WebSocket clients for a run."""
    if run_id not in active_websockets:
        return

    dead = []
    for ws in active_websockets[run_id]:
        try:
            await ws.send_json(event)
        except Exception:
            dead.append(ws)

    for ws in dead:
        active_websockets[run_id].remove(ws)


async def _run_research_background(run_id: str, req: ResearchRequest):
    """Background task that runs the full research pipeline and streams events."""
    logger.info(f"Starting background research run {run_id}")

    async def event_callback(event: dict):
        """Forward pipeline events to WebSocket clients."""
        logger.info(
            f"[run {run_id}] {event.get('event', '')} "
            f"layer={event.get('layer', '')} agent={event.get('agent', '')} "
            f"message={event.get('message', '')}"
        )
        await _broadcast_event(run_id, event)

    try:
        output_mode = _effective_output_mode(req)
        result = await run_research(
            input=ResearchInput(
                query=req.query,
                input_type=req.input_type,
                user_id=req.user_id,
                context=req.context,
                output_mode=output_mode,
                product=output_mode,
                lens_preferences=req.lens_preferences,
            ),
            config=_config_from_request(req),
            context=req.context,
            run_id=run_id,
            event_callback=event_callback,
        )
        if output_mode in {"ladderflow", "ladderbrief"}:
            legacy = await run_legacy_shadow(req.query, req.user_id, output_mode)
            result.shadow_comparison = compare_shadow_outputs(result, legacy)
        runs[run_id] = result
        await save_research_result(result, query=req.query, user_id=req.user_id, product=output_mode)
        await maybe_send_cost_alert(result)

        # Send final result
        await _broadcast_event(run_id, {
            "event": "complete",
            "data": _serialize(result),
        })

    except Exception as e:
        logger.error(f"Research run {run_id} failed: {e}", exc_info=True)
        error_result = ResearchResult(run_id=run_id, status="error", error=str(e))
        runs[run_id] = error_result
        await save_research_result(error_result, query=req.query, user_id=req.user_id, product=_effective_output_mode(req))

        await _broadcast_event(run_id, {
            "event": "error",
            "message": str(e),
        })


# ──────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────

def main():
    import uvicorn
    uvicorn.run(
        "research_agent.main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
        log_level="info",
    )


if __name__ == "__main__":
    main()
