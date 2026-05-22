import unittest
from unittest.mock import patch

from research_agent.graph.verification import _claim_type, verification_node
from research_agent.models import CostBreakdown, SourceRef, Thesis


class VerificationTests(unittest.IsolatedAsyncioTestCase):
    def test_claim_type_detection(self):
        self.assertEqual(_claim_type("AI adoption increased by 42% in 2025."), "statistic")
        self.assertEqual(_claim_type('Sam said "agents are the future."'), "attributed_quote")
        self.assertEqual(_claim_type("AI agents are changing sales workflows."), "factual_assertion")
        self.assertEqual(_claim_type("A better way to think about agents."), "opinion")

    async def test_verifies_claim_against_sources(self):
        state = {
            "winning_thesis": Thesis(
                lens="strategy",
                statement="AI agents increased sales workflow automation by 42%.",
                supporting_points=[],
            ),
            "sources": [
                SourceRef(
                    title="AI agents increased sales workflow automation by 42%",
                    url="https://example.com/report",
                    snippet="A report says AI agents increased sales workflow automation by 42%.",
                    platform="web",
                    relevance_score=0.9,
                )
            ],
            "cost": CostBreakdown(run_id="run-1"),
        }

        result = await verification_node(state)

        self.assertTrue(result["verified"])
        self.assertEqual(result["verification_notes"][0]["verdict"], "verified")
        self.assertEqual(result["verification_notes"][0]["evidence_urls"], ["https://example.com/report"])

    async def test_unverifiable_material_claim_fails(self):
        async def fake_web_search(query, max_results=3):
            return []

        state = {
            "winning_thesis": Thesis(
                lens="strategy",
                statement="AI agents increased sales workflow automation by 42%.",
                supporting_points=[],
            ),
            "sources": [],
            "cost": CostBreakdown(run_id="run-1"),
        }

        with patch("research_agent.graph.verification.web_search", fake_web_search):
            result = await verification_node(state)

        self.assertFalse(result["verified"])
        self.assertEqual(result["verification_notes"][0]["verdict"], "unverifiable")


if __name__ == "__main__":
    unittest.main()
