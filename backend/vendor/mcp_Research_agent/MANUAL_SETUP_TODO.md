# Manual Setup TODO

Only pending items are listed here. Completed setup has been removed.

Run the app:

```powershell
.\.venv\Scripts\python.exe -m research_agent.main
```

## 1. Reddit Relevance Quality

Reddit/ScrapeCreators works, but some fallback results are irrelevant.

- Tighten Reddit fallback filtering so irrelevant subreddits/posts are not used.
- Prefer posts with strong query-term matches in title/snippet.
- Consider adding a curated subreddit allowlist for technical/business topics.

## 3. Creator Knowledge Graph Data

Supabase persistence works, but production creator context still needs real data.

- Create/verify `creator_profiles` if using Supabase-backed KG:

```sql
create table if not exists creator_profiles (
    user_id text primary key,
    context_json jsonb not null
);
```

- Insert real creator context rows for LadderFlow and Ladder Brief users.


## 6. Optional Production Ops

These are optional, not blockers for local operation.

- Set `LANGSMITH_API_KEY` for tracing.
- Set `SLACK_WEBHOOK_URL` for cost/spend alerts.
- Run one real YouTube comments fallback through Apify if you want Apify fallback enabled in production.

