import unittest
from unittest.mock import patch

from research_agent.graph.analysis import kg_filter_node, scoring_node
from research_agent.graph.demand import demand_side_node
from research_agent.graph.synthesis import synthesis_node
from research_agent.knowledge_graph import CreatorKG
from research_agent.models import CostBreakdown, ResearchConfig, SourceRef
from research_agent.tools.supadata import _source_from_supadata_search_item


class FixtureKG(CreatorKG):
    async def get_user_context(self, user_id: str) -> dict:
        return {"past_topics": ["old topic"], "audience_description": "fixture"}

    async def gap_score(self, topic: str, user_id: str) -> float:
        return 0.25

    async def saturation_score(self, topic: str, user_id: str) -> float:
        return 0.75


class ContractAndScoringTests(unittest.IsolatedAsyncioTestCase):
    async def test_kg_filter_uses_injected_kg(self):
        state = {
            "query": "AI research agents",
            "user_id": "user-1",
            "knowledge_graph": FixtureKG(),
        }

        result = await kg_filter_node(state)

        self.assertEqual(result["kg_gap"], 0.25)
        self.assertEqual(result["kg_saturation"], 0.75)
        self.assertEqual(result["user_context"]["audience_description"], "fixture")

    async def test_scoring_rejects_single_platform_topic(self):
        state = {
            "query": "AI research agents",
            "sources": [
                SourceRef(
                    title="Only one platform",
                    url="https://example.com",
                    snippet="example",
                    platform="web",
                    relevance_score=0.9,
                )
            ],
            "kg_gap": 0.8,
            "kg_saturation": 0.0,
        }

        result = await scoring_node(state)

        self.assertFalse(result["topic_passed"])
        self.assertIn("2 required", result["rejection_reason"])
        self.assertEqual(result["score_breakdown"]["platform_count"], 1)

    async def test_synthesis_skips_rejected_topic(self):
        state = {
            "query": "AI research agents",
            "topic_passed": False,
            "rejection_reason": "not enough platforms",
            "cost": CostBreakdown(run_id="run-1"),
        }

        result = await synthesis_node(state)

        self.assertIsNone(result["winning_thesis"])
        self.assertEqual(result["candidate_theses"], [])
        self.assertEqual(result["cost"].total, 0.0)

    async def test_synthesis_skips_when_cost_ceiling_reached(self):
        cost = CostBreakdown(run_id="run-1")
        cost.add_cost("demand_side", "tool", "tool", 1.0)
        state = {
            "query": "AI research agents",
            "topic_passed": True,
            "config": ResearchConfig(cost_ceiling=0.5),
            "cost": cost,
        }

        result = await synthesis_node(state)

        self.assertIsNone(result["winning_thesis"])
        self.assertIn("Cost ceiling reached", result["rejection_reason"])

    async def test_demand_side_honors_skip_platforms(self):
        state = {
            "query": "AI research agents",
            "config": ResearchConfig(skip_platforms=["web", "reddit", "youtube", "hackernews", "paa", "supadata"]),
            "cost": CostBreakdown(run_id="run-1"),
        }

        result = await demand_side_node(state)

        self.assertEqual(result["sources"], [])
        self.assertEqual(result["comments_raw"], [])

    async def test_paa_autocomplete_is_returned_as_sources(self):
        async def fake_search_paa(query, max_results=10, cost_tracker=None):
            return []

        async def fake_autocomplete(query, max_results=10):
            return ["ai research agents examples"]

        state = {
            "query": "AI research agents",
            "config": ResearchConfig(skip_platforms=["web", "reddit", "youtube", "hackernews", "supadata"]),
            "cost": CostBreakdown(run_id="run-1"),
        }

        with patch("research_agent.graph.demand.search_paa", fake_search_paa), patch(
            "research_agent.graph.demand.search_autocomplete", fake_autocomplete
        ):
            result = await demand_side_node(state)

        self.assertEqual(len(result["sources"]), 1)
        self.assertEqual(result["sources"][0].title, "ai research agents examples")
        self.assertEqual(result["sources"][0].engagement["type"], "autocomplete")

    async def test_reddit_runs_top_controversial_and_emerging_sorts(self):
        sorts = []

        async def fake_search_reddit(query, subreddits=None, max_results=15, sort="top", min_score=None, max_age_days=None, cost_tracker=None):
            sorts.append((sort, max_age_days))
            return [
                SourceRef(
                    title=f"AI research agents {sort} result",
                    url=f"https://reddit.com/r/test/{sort}",
                    snippet="reddit source",
                    platform="reddit",
                    relevance_score=0.8,
                )
            ]

        async def fake_comments(permalink, limit=50):
            return []

        state = {
            "query": "AI research agents",
            "config": ResearchConfig(skip_platforms=["web", "youtube", "hackernews", "paa", "supadata"]),
            "cost": CostBreakdown(run_id="run-1"),
        }

        with patch("research_agent.graph.demand.search_reddit", fake_search_reddit), patch(
            "research_agent.graph.demand.fetch_reddit_comments", fake_comments
        ):
            result = await demand_side_node(state)

        self.assertEqual({sort for sort, _ in sorts}, {"top", "controversial", "new"})
        self.assertIn(("new", 7), sorts)
        self.assertEqual(len(result["sources"]), 3)

    async def test_supadata_transcripts_are_returned_as_sources_and_comments(self):
        async def fake_supadata(query, max_results=5, cost_tracker=None):
            return [
                SourceRef(
                    title="Transcript: AI research agents",
                    url="https://youtube.com/watch?v=abc12345678",
                    snippet="transcript text",
                    platform="supadata",
                    relevance_score=0.8,
                )
            ], [{"body": "transcript chunk", "platform": "supadata"}]

        state = {
            "query": "AI research agents",
            "config": ResearchConfig(skip_platforms=["web", "reddit", "youtube", "hackernews", "paa"]),
            "cost": CostBreakdown(run_id="run-1"),
        }

        with patch("research_agent.graph.demand.search_supadata_transcripts", fake_supadata):
            result = await demand_side_node(state)

        self.assertEqual(len(result["sources"]), 1)
        self.assertEqual(result["sources"][0].platform, "supadata")
        self.assertEqual(result["comments_raw"][0]["platform"], "supadata")

    def test_supadata_youtube_search_item_maps_to_youtube_source(self):
        source = _source_from_supadata_search_item({
            "id": "abc12345678",
            "title": "AI research agents explained",
            "description": "A practical walkthrough",
            "viewCount": 25000,
            "likeCount": 1200,
            "commentCount": 80,
            "uploadDate": "2026-05-01T00:00:00.000Z",
            "duration": 420,
            "channel": {"id": "channel-1", "name": "Ladder"},
        })

        self.assertEqual(source.platform, "youtube")
        self.assertEqual(source.url, "https://youtube.com/watch?v=abc12345678")
        self.assertEqual(source.engagement["provider"], "supadata")
        self.assertEqual(source.engagement["views"], 25000)
        self.assertEqual(source.engagement["channel_title"], "Ladder")


if __name__ == "__main__":
    unittest.main()
