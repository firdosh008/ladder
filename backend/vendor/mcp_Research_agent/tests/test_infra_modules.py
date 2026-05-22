import unittest

from research_agent.eval import EvalCase, score_eval_case
from research_agent.models import CostBreakdown, ResearchResult, SourceRef, Thesis
from research_agent.ops import _distribution
from research_agent.rollout import compare_shadow_outputs
from research_agent.storage import _to_jsonable


class InfraModuleTests(unittest.TestCase):
    def test_distribution(self):
        dist = _distribution([1, 2, 3, 4])
        self.assertEqual(dist["avg"], 2.5)
        self.assertGreater(dist["p95"], dist["p50"])

    def test_shadow_comparison(self):
        result = ResearchResult(
            winning_thesis=Thesis(lens="strategy", statement="A thesis"),
            sources=[SourceRef(title="s", url="https://x.com", snippet="", platform="web")],
            cost_breakdown=CostBreakdown(total=0.25),
            status="complete",
        )
        comparison = compare_shadow_outputs(result, {"summary": "legacy"})
        self.assertTrue(comparison["legacy_available"])
        self.assertEqual(comparison["unified_thesis"], "A thesis")

    def test_eval_scoring(self):
        result = ResearchResult(
            winning_thesis=Thesis(
                lens="strategy",
                statement="AI agents need evaluation for sales workflow trust.",
                supporting_points=["Evaluation builds trust."],
            ),
            score_breakdown={"platform_count": 2},
            status="complete",
        )
        case = EvalCase(
            id="case",
            query="AI agents",
            expected_supporting_points=["evaluation", "sales workflow"],
            topics_to_avoid=["generic listicle"],
        )
        scored = score_eval_case(case, result)
        self.assertEqual(scored["cross_platform_corroboration"], 1.0)
        self.assertEqual(scored["avoid_false_positive"], 1.0)

    def test_storage_jsonable(self):
        result = ResearchResult(
            winning_thesis=Thesis(lens="signal", statement="Signal"),
            status="complete",
        )
        payload = _to_jsonable(result)
        self.assertEqual(payload["winning_thesis"]["statement"], "Signal")


if __name__ == "__main__":
    unittest.main()
