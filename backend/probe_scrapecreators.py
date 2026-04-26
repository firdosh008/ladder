"""One-off probe to verify the ScrapeCreators API key works against
Reddit / YouTube / X. Delete once the real providers land.

Run from backend/:
    uv run python probe_scrapecreators.py
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

API_KEY = os.environ["SCRAPECREATORS_API_KEY"]
BASE = "https://api.scrapecreators.com"
HEADERS = {"x-api-key": API_KEY}


async def call(
    client: httpx.AsyncClient, path: str, params: dict[str, str]
) -> tuple[int, str]:
    r = await client.get(f"{BASE}{path}", params=params, headers=HEADERS, timeout=30)
    body = r.text
    return r.status_code, body[:400] + ("…" if len(body) > 400 else "")


async def main() -> None:
    async with httpx.AsyncClient() as client:
        results = await asyncio.gather(
            call(
                client,
                "/v1/reddit/subreddit",
                {
                    "subreddit": "startups",
                    "sort": "top",
                    "timeframe": "week",
                    "trim": "true",
                },
            ),
            call(
                client,
                "/v1/youtube/search",
                {
                    "query": "ai agents",
                    "uploadDate": "this_week",
                    "sortBy": "popular",
                    "type": "videos",
                },
            ),
            call(
                client,
                "/v1/twitter/user-tweets",
                {"handle": "OpenAI", "trim": "true"},
            ),
        )

    for name, (status, preview) in zip(("reddit", "youtube", "x"), results):
        ok = "OK  " if 200 <= status < 300 else "FAIL"
        print(f"[{ok}] {name:<8} status={status}")
        print(f"       {preview}\n")


if __name__ == "__main__":
    asyncio.run(main())
