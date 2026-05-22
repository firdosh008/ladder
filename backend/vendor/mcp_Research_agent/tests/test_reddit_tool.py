import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from research_agent.tools.reddit import _is_relevant_reddit_post, _scrape_creators_search


class FakeResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return {
            "posts": [
                {
                    "title": "AI agents in content workflows",
                    "permalink": "/r/test/comments/1/post/",
                    "selftext": "Teams are using artificial intelligence agents for content creation.",
                    "subreddit": "test",
                    "score": 25,
                    "created_utc": datetime.now(timezone.utc).timestamp(),
                }
            ]
        }


class FakeAsyncClient:
    last_headers = None
    last_params = None

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def get(self, *args, **kwargs):
        FakeAsyncClient.last_headers = kwargs.get("headers")
        FakeAsyncClient.last_params = kwargs.get("params")
        return FakeResponse()


class RedditToolTests(unittest.IsolatedAsyncioTestCase):
    async def test_scrape_creators_uses_expected_auth_header_and_sort(self):
        with patch("research_agent.tools.reddit.settings.scrape_creators_api_key", "token"), patch(
            "research_agent.tools.reddit.httpx.AsyncClient", FakeAsyncClient
        ):
            results = await _scrape_creators_search(
                "AI agents",
                subreddits=None,
                max_results=5,
                sort="controversial",
                min_score=1,
                cutoff=datetime(2020, 1, 1, tzinfo=timezone.utc),
            )

        self.assertEqual(len(results), 1)
        self.assertEqual(FakeAsyncClient.last_headers, {"x-api-key": "token"})
        self.assertEqual(FakeAsyncClient.last_params["sort"], "comment_count")

    def test_relevance_filter_rejects_weak_query_match(self):
        post = {
            "title": "Claude-powered coding incident",
            "selftext": "A developer deleted files during an unrelated automation test.",
            "subreddit": "technology",
        }

        self.assertFalse(_is_relevant_reddit_post(post, "AI agents for content creation"))

    def test_relevance_filter_accepts_strong_title_or_body_match(self):
        post = {
            "title": "AI agents for content creation",
            "selftext": "How teams use LLM workflows for content research and drafting.",
            "subreddit": "SaaS",
        }

        self.assertTrue(_is_relevant_reddit_post(post, "AI agents for content creation"))

    def test_relevance_filter_honors_subreddit_allowlist(self):
        post = {
            "title": "AI agents for content creation",
            "selftext": "Strong topical match.",
            "subreddit": "technology",
        }

        with patch("research_agent.tools.reddit.settings.reddit_allowed_subreddits", "SaaS,startups"):
            self.assertFalse(_is_relevant_reddit_post(post, "AI agents for content creation"))


if __name__ == "__main__":
    unittest.main()
