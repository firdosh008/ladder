"""Evaluation harness for the unified research agent."""

from __future__ import annotations

import argparse
import asyncio
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from research_agent.graph.orchestrator import run_research
from research_agent.models import ResearchConfig, ResearchInput


@dataclass
class EvalCase:
    id: str
    query: str
    user_id: str = "eval"
    output_mode: str = "research_report"
    product: str = "research_report"
    context: dict[str, Any] | None = None
    expected_thesis: str = ""
    expected_supporting_points: list[str] | None = None
    topics_to_avoid: list[str] | None = None


async def run_eval_dataset(path: str, subset: int | None = None) -> dict[str, Any]:
    cases = load_eval_cases(path)
    if subset:
        cases = cases[:subset]

    results = []
    for case in cases:
        result = await run_research(
            input=ResearchInput(
                query=case.query,
                user_id=case.user_id,
                context=case.context or {},
                output_mode=case.output_mode,
                product=case.product,
            ),
            context=case.context or {},
            config=ResearchConfig(cost_ceiling=3.0),
        )
        results.append(score_eval_case(case, result))

    return {
        "cases": len(results),
        "averages": _average_metrics(results),
        "results": results,
    }


def load_eval_cases(path: str) -> list[EvalCase]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return [
        EvalCase(
            id=item["id"],
            query=item["query"],
            user_id=item.get("user_id", "eval"),
            output_mode=item.get("output_mode", item.get("product", "research_report")),
            product=item.get("product", item.get("output_mode", "research_report")),
            context=item.get("context", None),
            expected_thesis=item.get("expected_thesis", ""),
            expected_supporting_points=item.get("expected_supporting_points", []),
            topics_to_avoid=item.get("topics_to_avoid", []),
        )
        for item in raw
    ]


def score_eval_case(case: EvalCase, result) -> dict[str, Any]:
    actual_text = " ".join([
        result.winning_thesis.statement if result.winning_thesis else "",
        *([] if not result.winning_thesis else result.winning_thesis.supporting_points),
    ])
    expected_points = case.expected_supporting_points or []
    avoid = case.topics_to_avoid or []

    coverage = _coverage(expected_points, actual_text)
    avoid_hits = sum(1 for topic in avoid if _contains_topic(actual_text, topic))
    precision_proxy = 1.0 if result.winning_thesis and result.winning_thesis.statement else 0.0
    corroboration = 1.0 if result.score_breakdown.get("platform_count", 0) >= 2 else 0.0

    return {
        "id": case.id,
        "status": result.status,
        "coverage": coverage,
        "precision_proxy": precision_proxy,
        "cross_platform_corroboration": corroboration,
        "avoid_false_positive": 1.0 if avoid_hits == 0 else 0.0,
        "cost": result.cost_breakdown.total,
        "latency_seconds": result.cost_breakdown.duration_seconds,
    }


def _coverage(expected_points: list[str], actual_text: str) -> float:
    if not expected_points:
        return 0.0
    hits = sum(1 for point in expected_points if _contains_topic(actual_text, point))
    return hits / len(expected_points)


def _contains_topic(text: str, topic: str) -> bool:
    text_tokens = set(re.findall(r"[a-z0-9]+", text.lower()))
    topic_tokens = {token for token in re.findall(r"[a-z0-9]+", topic.lower()) if len(token) > 3}
    if not topic_tokens:
        return False
    return len(text_tokens & topic_tokens) / len(topic_tokens) >= 0.5


def _average_metrics(results: list[dict[str, Any]]) -> dict[str, float]:
    keys = [
        "coverage", "precision_proxy", "cross_platform_corroboration",
        "avoid_false_positive", "cost", "latency_seconds",
    ]
    return {
        key: round(sum(result[key] for result in results) / len(results), 4) if results else 0.0
        for key in keys
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset", help="Path to eval dataset JSON")
    parser.add_argument("--subset", type=int, default=None)
    args = parser.parse_args()
    print(json.dumps(asyncio.run(run_eval_dataset(args.dataset, args.subset)), indent=2))


if __name__ == "__main__":
    main()
