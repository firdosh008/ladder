"""HTTP API for experimental diagram-generation pipeline."""

from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.agents.diagram import DiagramPipelineError, run_diagram_pipeline
from app.agents.diagram.models import DiagramBrandTheme
from app.middleware.auth import current_user

router = APIRouter(prefix="/diagrams", tags=["diagrams"])


def _norm_theme_hex(v: str) -> str:
    s = v.strip()
    if not s.startswith("#"):
        s = f"#{s}"
    return s if re.match(r"^#[0-9A-Fa-f]{6}$", s) else "#3B82F6"


class BrandThemeRequest(BaseModel):
    primary: str = Field(min_length=4, max_length=32)
    secondary: str = Field(min_length=4, max_length=32)
    accent: str = Field(min_length=4, max_length=32)
    text: str = Field(min_length=4, max_length=32)
    background: str = Field(min_length=4, max_length=32)
    font: str = Field(min_length=1, max_length=120)


class DiagramGenerateRequest(BaseModel):
    text: str = Field(min_length=10, max_length=60_000)
    seed: int = Field(default=42, ge=0, le=2_147_483_647)
    brand_accent_hex: str | None = Field(
        default=None,
        description='Optional RRGGBB without "#" — shorthand for primary+accent.',
        max_length=6,
        min_length=6,
        pattern=r"^[0-9a-fA-F]{6}$",
    )
    brand: BrandThemeRequest | None = Field(
        default=None,
        description="Full brand palette + font — overrides hardcoded defaults when set.",
    )


class DiagramGenerateResponse(BaseModel):
    scene: dict
    validation_score: int = Field(description="Last multimodal critic numeric grade")
    final_score: int = Field(description="Repeated from debug for convenience")
    validation_issues: list[dict[str, Any]]
    validation_suggestions: list[str]
    agent_debug: dict
    iterations: int


def _theme_from_request(body: DiagramGenerateRequest) -> DiagramBrandTheme | None:
    if body.brand:
        b = body.brand
        return DiagramBrandTheme(
            primary=_norm_theme_hex(b.primary),
            secondary=_norm_theme_hex(b.secondary),
            accent=_norm_theme_hex(b.accent),
            text=_norm_theme_hex(b.text),
            background=_norm_theme_hex(b.background),
            font=b.font.strip()[:120],
        )
    return None


@router.post("/generate", response_model=DiagramGenerateResponse)
async def generate_diagram(
    body: DiagramGenerateRequest,
    ctx: tuple = Depends(current_user),
) -> DiagramGenerateResponse:
    """Run strategist → planner → graph repair → layout → Excali skeleton → critic loop.

    Outputs a ``SceneSkeleton``-compatible JSON graph (no coords from LLMs).
    """
    del ctx  # auth — side effect only

    accent = body.brand_accent_hex.strip() if body.brand_accent_hex else None
    theme = _theme_from_request(body)
    try:
        scene, debug, critique = await run_diagram_pipeline(
            body.text.strip(),
            seed=body.seed,
            brand_accent=accent,
            brand_theme=theme,
        )
    except DiagramPipelineError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(
            status_code=502,
            detail=f"diagram generation upstream failed: {e}",
        ) from e

    issue_rows = [{"kind": i.kind, "severity": i.severity} for i in critique.issues]
    last_it = debug.layout_configs_per_iteration[-1] if debug.layout_configs_per_iteration else None
    agent_debug = {
        "strategist": debug.strategist.model_dump(),
        "planner_versions": [p.model_dump(by_alias=True) for p in debug.planner_versions],
        "layout_configs_per_iteration": [
            lc.model_dump() for lc in debug.layout_configs_per_iteration
        ],
        "geometry_issues_per_iteration": [
            [g.model_dump() for g in bucket] for bucket in debug.geometry_issues_per_iteration
        ],
        "geometry_validation_per_iteration": [
            it.model_dump() for it in debug.iteration_debug
        ],
        "critic_runs": [c.model_dump() for c in debug.critic_runs],
        "final_score": debug.final_score,
        "render_png_paths_per_iteration": debug.render_png_paths_per_iteration,
        "token_usage": debug.token_usage.model_dump(),
        "layout_type": last_it.layout_archetype if last_it else None,
        "brand_theme": debug.brand_theme.model_dump() if debug.brand_theme else None,
        "node_layout": [n.model_dump() for n in debug.node_layout_final],
        "edges": debug.edges_final,
    }
    return DiagramGenerateResponse(
        scene=scene.model_dump(by_alias=False),
        validation_score=critique.score,
        final_score=debug.final_score,
        validation_issues=issue_rows,
        validation_suggestions=list(critique.suggestions),
        agent_debug=agent_debug,
        iterations=debug.iterations_used,
    )
