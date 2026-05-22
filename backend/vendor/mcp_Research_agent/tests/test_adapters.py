import unittest

from research_agent.adapters import adapt_research_output
from research_agent.models import CommentCluster, Gap, SupplySideReport, Thesis


class AdapterTests(unittest.TestCase):
    def test_ladderflow_adapter_outputs_podcast_outline(self):
        thesis = Thesis(
            lens="strategy",
            statement="AI agents need operator-grade evals.",
            supporting_points=["Eval failures are deployment failures.", "Teams need monitoring."],
        )
        output = adapt_research_output("ladderflow", thesis, [], SupplySideReport(), [
            CommentCluster(theme="Need real examples", unmet_ask=True, frequency=4)
        ])

        self.assertEqual(output["format"], "podcast_outline")
        self.assertEqual(output["opening_hook"], thesis.statement)
        self.assertGreaterEqual(len(output["interview_questions"]), 2)
        self.assertEqual(output["unmet_asks_to_probe"], ["Need real examples"])

    def test_ladderbrief_adapter_outputs_canvas_outline(self):
        thesis = Thesis(
            lens="signal",
            statement="Comment sentiment is the leading indicator.",
            supporting_points=["Disappointed comments reveal gaps."],
        )
        output = adapt_research_output("ladderbrief", thesis, [], SupplySideReport(gaps=[
            Gap(gap_type="depth", confidence=0.8, description="Top videos are shallow.")
        ]), [])

        self.assertEqual(output["format"], "canvas_outline")
        self.assertEqual(output["nodes"][0]["type"], "thesis")
        self.assertTrue(any(node["type"] == "sticky_note" for node in output["nodes"]))
        self.assertTrue(output["edges"])


if __name__ == "__main__":
    unittest.main()
