import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from research_agent.graph.analysis import _detect_supply_gaps, _estimate_supply_saturation
from research_agent.models import CostBreakdown
from research_agent.models import ContentItem, SourceRef, SupplySideReport
from research_agent.scoring import score_topic
from research_agent.tools.youtube import (
    extract_youtube_video_id,
    fetch_youtube_comments,
    fetch_youtube_comments_apify,
    parse_youtube_duration,
)


def days_ago(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


class SupplySideAnalysisTests(unittest.TestCase):
    def test_parse_youtube_duration(self):
        self.assertEqual(parse_youtube_duration("PT1H2M3S"), 3723)
        self.assertEqual(parse_youtube_duration("PT12M"), 720)
        self.assertEqual(parse_youtube_duration("PT45S"), 45)
        self.assertEqual(parse_youtube_duration(""), 0)

    def test_extract_youtube_video_id(self):
        self.assertEqual(extract_youtube_video_id("https://youtube.com/watch?v=abcdefghijk"), "abcdefghijk")
        self.assertEqual(extract_youtube_video_id("https://youtu.be/abcdefghijk"), "abcdefghijk")
        self.assertEqual(extract_youtube_video_id("https://youtube.com/shorts/abcdefghijk"), "abcdefghijk")

    def test_detects_recency_format_depth_and_sentiment_gaps(self):
        content = [
            ContentItem(
                title=f"Video {idx}",
                url=f"https://youtube.com/watch?v=video00000{idx}",
                views=10_000,
                likes=100,
                comments_count=50,
                published_date=days_ago(700),
                duration_seconds=1200,
                engagement_ratio=0.02,
                sentiment_score=0.25,
            )
            for idx in range(4)
        ]
        content.append(ContentItem(
            title="Short shallow video",
            url="https://youtube.com/watch?v=video000005",
            views=8_000,
            likes=80,
            comments_count=40,
            published_date=days_ago(30),
            duration_seconds=240,
            engagement_ratio=0.015,
            sentiment_score=0.35,
        ))
        comments_by_url = {
            item.url: [
                {
                    "body": (
                        "This is interesting but I still do not understand the implementation details, "
                        "the tradeoffs, the failure modes, or how to apply it in a real production workflow. "
                        "The examples skip architecture, data quality, monitoring, evaluation, rollout, and "
                        "the operational constraints that determine whether this works outside a demo."
                    ),
                    "score": 10,
                }
            ]
            for item in content
        }

        gaps = _detect_supply_gaps("AI agents for sales automation", content, comments_by_url)
        gap_types = {gap.gap_type for gap in gaps}

        self.assertIn("recency", gap_types)
        self.assertIn("format", gap_types)
        self.assertIn("depth", gap_types)
        self.assertIn("sentiment", gap_types)

    def test_saturation_decreases_when_gaps_are_present(self):
        content = [
            ContentItem(title="Video", url="https://example.com", engagement_ratio=0.05)
            for _ in range(10)
        ]
        no_gap_saturation = _estimate_supply_saturation(content, [])
        gaps = _detect_supply_gaps("AI agents", [
            ContentItem(
                title="Old video",
                url="https://example.com/old",
                published_date=days_ago(800),
                engagement_ratio=0.05,
            )
            for _ in range(10)
        ], {})
        gap_saturation = _estimate_supply_saturation(content, gaps)

        self.assertLess(gap_saturation, no_gap_saturation)

    def test_blue_ocean_penalty_when_large_creators_dominate(self):
        report = SupplySideReport(
            top_content=[
                ContentItem(
                    title=f"Dominant creator {idx}",
                    url=f"https://example.com/{idx}",
                    views=20_000,
                    channel_subscribers=100_000,
                )
                for idx in range(5)
            ]
        )
        sources = [
            SourceRef(title="web", url="https://web.example", snippet="topic", platform="web", relevance_score=0.9),
            SourceRef(title="yt", url="https://yt.example", snippet="topic", platform="youtube", relevance_score=0.9),
        ]

        result = score_topic("AI agents", sources=sources, supply_report=report)

        self.assertGreater(result.size_mismatch, 0)
        self.assertTrue(result.passed)


class FakeApifyResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return [
            {"text": "This helped, but I wanted a much deeper implementation walkthrough.", "likeCount": 4},
            {"commentText": "Still confused about monitoring and production failures.", "likes": 2},
        ]


class FakeAsyncClient:
    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def post(self, *args, **kwargs):
        return FakeApifyResponse()


class ApifyFallbackTests(unittest.IsolatedAsyncioTestCase):
    async def test_apify_youtube_comments_tracks_cost(self):
        cost = CostBreakdown(run_id="run-1")
        with patch("research_agent.tools.youtube.settings.apify_api_key", "token"), patch(
            "research_agent.tools.youtube.httpx.AsyncClient", FakeAsyncClient
        ):
            comments = await fetch_youtube_comments_apify("abcdefghijk", limit=10, cost_tracker=cost)

        self.assertEqual(len(comments), 2)
        self.assertEqual(comments[0]["platform"], "youtube")
        self.assertGreater(cost.tool_costs["apify:youtube_comments"], 0)

    async def test_fetch_youtube_comments_prefers_apify_provider(self):
        async def fake_get_json(cache_key):
            return None

        async def fake_set_json(cache_key, value, ttl):
            return None

        with patch("research_agent.tools.youtube.settings.youtube_comments_provider", "apify"), patch(
            "research_agent.tools.youtube.settings.apify_api_key", "token"
        ), patch("research_agent.tools.youtube.settings.youtube_api_key", "youtube-token"), patch(
            "research_agent.tools.youtube.httpx.AsyncClient", FakeAsyncClient
        ), patch("research_agent.tools.youtube.get_json", fake_get_json), patch(
            "research_agent.tools.youtube.set_json", fake_set_json
        ):
            comments = await fetch_youtube_comments("abcdefghijk", limit=10)

        self.assertEqual(len(comments), 2)
        self.assertIn("deeper implementation", comments[0]["body"])


if __name__ == "__main__":
    unittest.main()
