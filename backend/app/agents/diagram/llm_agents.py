"""LLM-backed diagram agents (semantics only — graph / critique, no coords)."""

from __future__ import annotations

import json

from app.agents.diagram.llm import structured_json_call
from app.agents.diagram.models import (
    PlannerEdge,
    PlannerNode,
    PlannerOutput,
    StrategistOutput,
    VisualCriticOutput,
)


STRATEGIST_SYSTEM = """You are a diagram strategist.

Given a script or explanation you must propose how to VISUALISE it inside a concise diagram — do not sketch coordinates.

Return JSON ONLY via the constrained schema."""

STRATEGIST_USER_TEMPLATE = """Source material:

{payload}

Respond with strategist JSON:
1. Identify the core idea that must pop visually ('aha moment').
2. Pick one diagram archetype: process | system | hierarchy | timeline | comparison.
3. One-sentence core message.
4. 2–24 major nouns/phrases that should appear as elements."""


async def run_strategist(source_text: str) -> tuple[StrategistOutput, int, int]:
    u = STRATEGIST_USER_TEMPLATE.format(payload=source_text[:48_000])
    return await structured_json_call(STRATEGIST_SYSTEM, u, StrategistOutput, temperature=0.4)


PLANNER_SYSTEM = """You are a diagram planner.

Convert the strategist output into a structured graph ONLY:
- nodes: entities with ids, labels, types exactly one of main | secondary | small
  (main = focal stages or pillars, secondary = supporting items, small = minor labels)
- edges: directed relationships (`from`, `to`, optional edge label)

STRICT RULES:
- NEVER output numeric positions (no x/y/width/height).
- Exactly one node SHOULD have `"emphasis": true` — the hinge of the insight.
- 2–48 nodes unless the strategist list is trivially smaller.
- For comparison diagrams, populate `groups` so nodes split into exactly those columns.
- For hierarchy, one conceptual root (single source of truth)."""

PLANNER_USER_TEMPLATE = """Strategist plan (JSON-ish summary):
diagram_type={diagram_type}
core_message={core_message}
aha_moment={aha_moment}
components={components}

Original source excerpt (truncated):
{snippet}

Produce the planner JSON graph."""


async def run_planner(
    strategist: StrategistOutput, source_text: str
) -> tuple[PlannerOutput, int, int]:
    u = PLANNER_USER_TEMPLATE.format(
        diagram_type=strategist.diagram_type,
        core_message=strategist.core_message,
        aha_moment=strategist.aha_moment,
        components="; ".join(strategist.components),
        snippet=source_text[:12_000],
    )
    return await structured_json_call(PLANNER_SYSTEM, u, PlannerOutput, temperature=0.25)


def _extract_json_object(text: str) -> str:
    start = text.find("{")
    if start < 0:
        raise ValueError("no JSON object in critic response")
    depth = 0
    for i, ch in enumerate(text[start:], start=start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    raise ValueError("truncated JSON in critic response")


def _normalize_visual_payload(raw: dict) -> dict:
    issues = raw.get("issues")
    if isinstance(issues, list):
        for item in issues:
            if isinstance(item, dict) and "type" in item and "kind" not in item:
                item["kind"] = item.pop("type")
    return raw


async def run_visual_diagram_critic(
    png_path,
    strategist: StrategistOutput,
    planner: PlannerOutput,
    source_fragment: str,
) -> tuple[VisualCriticOutput, int, int]:
    """Multimodal critic — consumes the Pillow PNG + planner graph semantics."""

    import base64
    import re
    from pathlib import Path

    from anthropic import APIError

    from app.config import settings
    from app.services.llm import anthropic_client

    p = Path(str(png_path))
    if not p.is_file():
        raise FileNotFoundError(f"preview image missing: {p}")

    prompt = (
        f"You critique a raster diagram preview (Excalidraw skeleton fidelity).\n\n"
        f"Surface this aha visually: {strategist.aha_moment}\n"
        f"Headline tension: {strategist.core_message}\n\n"
        f"Source excerpt:\n{source_fragment[:6200]}\n\n"
        f"Planner graph topology (IDs + labels):\n"
        + json.dumps(
            {
                "nodes": [{"id": n.id, "label": n.label, "emphasis": n.emphasis} for n in planner.nodes],
                "edges": [
                    {"from": e.from_id, "to": e.to, "label": e.label} for e in planner.edges
                ],
            },
            ensure_ascii=False,
        )[:8000]
        + "\n\nReturn ONE JSON ONLY with keys:"
        '\nscore (1-10),\nissues: [{"kind":"<tag>","severity":"high"|"medium"|"low"}],'
        "\nlayout_actions: string[] actionable tokens,"
        '\n suggestions: concise human-readable tips.'
        "\nLayout action examples: increase_spacing, separate_clusters, "
        "change_layout_to_hierarchical, widen_canvas."
    )

    with open(p, "rb") as fh:
        b64 = base64.standard_b64encode(fh.read()).decode("ascii")

    client = anthropic_client()
    try:
        resp = await client.messages.create(
            model=settings.ANTHROPIC_MODEL,
            max_tokens=4096,
            temperature=0.15,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": b64,
                            },
                        },
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
        )
    except APIError as e:
        raise RuntimeError(f"vision critic API failed: {e}") from e

    blob = "".join(getattr(block, "text", "") or "" for block in resp.content)
    clean = blob
    clean = clean.replace("```json", "").replace("```", "")
    try:
        raw = json.loads(_extract_json_object(clean))
        if not isinstance(raw, dict):
            raise ValueError("not-object")
        raw = _normalize_visual_payload(raw)
        parsed = VisualCriticOutput.model_validate(raw)
    except (json.JSONDecodeError, ValueError) as je:
        m = re.search(r"\{[\s\S]*\}", blob)
        if not m:
            raise RuntimeError(f"vision critic JSON parse failed: {je}") from je
        raw = json.loads(m.group(0))
        parsed = VisualCriticOutput.model_validate(_normalize_visual_payload(raw))

    usage = getattr(resp, "usage", None)
    return parsed, int(getattr(usage, "input_tokens", 0) or 0), int(
        getattr(usage, "output_tokens", 0) or 0
    )


def minimal_planner_from_strategist(st: StrategistOutput) -> PlannerOutput:
    """Deterministic escape hatch when the LLM graph is unusable."""

    nodes: list[PlannerNode] = []
    for i, lab in enumerate(st.components[:24]):
        lab_t = (lab or "").strip()[:200]
        if not lab_t:
            continue
        nodes.append(
            PlannerNode(
                id=f"n{i + 1}",
                label=lab_t,
                type="main" if i == 0 else "secondary",
                emphasis=(i == 0),
            )
        )
    if len(nodes) < 2:
        nodes = [
            PlannerNode(id="n1", label=st.core_message[:200], type="main", emphasis=True),
            PlannerNode(id="n2", label=st.aha_moment[:200], type="secondary", emphasis=False),
        ]
    edges: list[PlannerEdge] = []
    for i in range(len(nodes) - 1):
        edges.append(
            PlannerEdge.model_validate(
                {"from": nodes[i].id, "to": nodes[i + 1].id, "label": None}
            )
        )
    return PlannerOutput(nodes=nodes, edges=edges, groups=[])


def normalize_planner_graph(
    planner: PlannerOutput, strategist: StrategistOutput
) -> PlannerOutput:
    """Dedupe IDs, coerce one emphasis fallback, prune orphan edges."""

    seen: set[str] = set()
    nodes_out: list[PlannerNode] = []
    for n in planner.nodes:
        nid = n.id.strip()[:64] or ""
        if not nid or nid in seen:
            continue
        seen.add(nid)
        nodes_out.append(n)
    if len(nodes_out) < 2:
        return minimal_planner_from_strategist(strategist)

    if not any(n.emphasis for n in nodes_out):
        best_i = -1
        best_len = 10_000
        for idx, node in enumerate(nodes_out):
            for comp in strategist.components:
                lc = comp.lower().strip()
                if lc and lc in node.label.lower():
                    ln = len(node.label)
                    if ln < best_len:
                        best_len = ln
                        best_i = idx
        if best_i >= 0:
            nodes_out[best_i] = nodes_out[best_i].model_copy(update={"emphasis": True})
        else:
            nodes_out[0] = nodes_out[0].model_copy(update={"emphasis": True})

    nid_set = {n.id for n in nodes_out}
    edges_ok = []
    seen_e = set()
    for e in planner.edges:
        if (
            e.from_id in nid_set
            and e.to in nid_set
            and e.from_id != e.to
            and (e.from_id, e.to) not in seen_e
        ):
            edges_ok.append(e)
            seen_e.add((e.from_id, e.to))

    grp_ok = [g for g in planner.groups if any(nid in nid_set for nid in g.node_ids)]
    return PlannerOutput(nodes=nodes_out, edges=edges_ok, groups=grp_ok)
