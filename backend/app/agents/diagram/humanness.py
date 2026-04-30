"""Deterministic perturbation — hand-drawn feel without LLM positions."""

from __future__ import annotations

import math
from random import Random

from app.models.db import SceneSkeleton, SceneSkeletonElement


def _id_mix(seed: int, el_id: str) -> int:
    acc = seed & 0x7FFFFFFF
    for c in el_id:
        acc = (acc * 131 + ord(c)) & 0x7FFFFFFF
    return acc


def apply_humanness(scene: SceneSkeleton, seed: int) -> SceneSkeleton:
    """Jitter geometric + style fields; preserve ids and topology.

    Rotation is intentionally omitted — ``SceneSkeletonElement`` has no rotation
    field in our persisted schema.
    """

    els: list[SceneSkeletonElement] = []
    for i, el in enumerate(scene.elements):
        rloc = Random(_id_mix(seed + i * 9176, el.id))
        dx = round(rloc.uniform(-5.0, 5.0), 3)
        dy = round(rloc.uniform(-5.0, 5.0), 3)
        rough = int(round(min(2, max(0, math.floor(rloc.uniform(0, 3))))))
        d = dict(el.model_dump(exclude_none=True))
        if el.type in {"rectangle", "text"}:
            d["x"] = float(el.x) + dx
            d["y"] = float(el.y) + dy
            d["roughness"] = rough
            if el.type == "rectangle" and el.strokeWidth is not None:
                bump = round(rloc.uniform(0, 0.35), 2)
                d["strokeWidth"] = float(
                    min(8.0, max(1.5, float(el.strokeWidth) + bump))
                )
        elif el.type == "arrow":
            d["x"] = float(el.x) + dx * 0.35
            d["y"] = float(el.y) + dy * 0.35
            d["roughness"] = rough
            if el.strokeWidth is not None:
                bump = round(rloc.uniform(0, 0.2), 2)
                d["strokeWidth"] = float(
                    min(8.0, max(1.5, float(el.strokeWidth) + bump))
                )
        els.append(SceneSkeletonElement.model_validate(d))
    return SceneSkeleton(
        canvas_width=scene.canvas_width,
        canvas_height=scene.canvas_height,
        background_color=scene.background_color,
        elements=els,
        notes=scene.notes,
        files=scene.files,
    )
