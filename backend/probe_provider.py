"""End-to-end smoke for app/providers/scrapecreators.py.

Verifies that the provider module reads SCRAPECREATORS_API_KEY via Settings
and returns the normalized dataclasses the tools expect.

Run from backend/:
    uv run python probe_provider.py
"""

from __future__ import annotations

import asyncio

from app.providers import scrapecreators


async def main() -> None:
    reddit, yt, x, ig = await asyncio.gather(
        scrapecreators.reddit_subreddit("startups", sort="top", timeframe="week", limit=2),
        scrapecreators.youtube_search("ai agents", upload_date="this_week", limit=2),
        scrapecreators.x_user_tweets("OpenAI", limit=2),
        scrapecreators.instagram_reels_search("startup", date_posted="last-month", limit=2),
    )

    print(f"\nReddit r/startups · top week ({len(reddit)})")
    for p in reddit:
        print(f"  [{p.score} ups, {p.num_comments} comments] {p.title[:80]}")
        print(f"         {p.url}")

    print(f"\nYouTube · 'ai agents' · this_week popular ({len(yt)})")
    for v in yt:
        print(f"  [{v.view_count_text or '?'}] {v.title[:80]}")
        print(f"         {v.url}")

    print(f"\nX · @OpenAI top tweets ({len(x)})")
    for t in x:
        likes = t.like_count or 0
        views = t.view_count or 0
        print(f"  [{likes} likes, {views} views] {t.text[:80]}")
        print(f"         {t.url}")

    print(f"\nInstagram · 'ai agents' · last-week ({len(ig)})")
    for r in ig:
        plays = r.play_count or 0
        likes = r.like_count or 0
        owner = r.owner_handle or "?"
        print(f"  [{plays} plays, {likes} likes, @{owner}] {r.caption[:80]}")
        print(f"         {r.url}")


if __name__ == "__main__":
    asyncio.run(main())
