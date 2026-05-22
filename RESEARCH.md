# Research & Fact-Checking System

## Research Agents (3 agents, sequential)

The research crew gathers 12-18 signals across 5 platforms, scores them, and produces 4-6 video idea drafts. All streaming via WebSocket to the frontend.

### Agent 1: Trend Researcher

Fires 6 tools in parallel to pull recent signals:

| Tool | Provider | Source | Quality Gate |
|---|---|---|---|
| `web_search` | **Exa** (exa-py, MIT) | Neural web search | Last 90 days, server-side freshness |
| `reddit_search` | **ScrapeCreators** API | Cross-Reddit keyword search | Score ≥10, ≤28 days old |
| `reddit_trending` | **ScrapeCreators** API | Top posts from discovered subreddits | Score ≥10, ranked by score/hour |
| `youtube_trending` | **ScrapeCreators** API | Recent videos | ≥5k views, ≤90 days, ranked by view-velocity |
| `x_user_tweets` | **ScrapeCreators** API | Top tweets from 2-3 handles | ≥30 engagement (likes + retweets×2) |
| `instagram_reels` | **ScrapeCreators** API | Reel search by keyword | ≥5k plays |

Each tool emits `SourceRef` dataclasses (title, URL, snippet, engagement metadata) via a ContextVar side-channel — the frontend sees source cards in real time while the crew runs. All sources are also collected server-side for verification later.

### Agent 2: Outlier Scorer

Scores each signal 0-100. Rules:
- Cross-platform corroboration: +10 when the same idea appears on 2+ platforms
- Knowledge graph gap detection: +5 when a signal fills territory the founder hasn't covered
- Generic/recycled takes rejected: <30 score dropped

### Agent 3: Idea Architect

Transforms top scored signals into 4-6 video idea drafts. Each draft: title, rationale, why_now, opportunity_score, outlier_score, suggested_tags.

Uses `output_pydantic=ResearchIdeas` for structured JSON output.

---

## Hallucination Prevention

### Layer 1 — Quality Gates (in tools, not the LLM)

Numeric thresholds run inside each tool before the agent sees any data. Posts below threshold are dropped — the LLM never reasons about junk. This is the first defense: bad data never enters the context window.

Thresholds: Reddit ≥10 score / ≤28 days, YouTube ≥5k views / ≤90 days, Instagram ≥5k plays / ≤90 days, X ≥30 engagement.

### Layer 2 — Freshness Enforcement

Every agent backstory includes the current UTC date. All search queries must include the current year. Exa is server-filtered to last 90 days. Prevents the model from surfacing 2023/2024 artifacts as "trends."

### Layer 3 — Knowledge Graph Cross-Referencing

Before research runs, the founder's accumulated knowledge (scripts, ideas, notes, extracts) is retrieved via pgvector cosine similarity (`match_knowledge_nodes` RPC, OpenAI `text-embedding-3-small`). Matching chunks are injected into Agent 2 and Agent 3 backstories so they:
- Avoid drafting ideas that duplicate what the founder already covered
- Reward signals that fill knowledge gaps

### Layer 4 — Platform-Aware Source Citations

All research sources (not just the first 20) are passed to the script writer with platform labels. The prompt explicitly teaches the model which platform to cite for which claim type:

- **web** → statistics, research findings, market data (cite for numbers)
- **reddit** → community sentiment, user experiences, pain points (cite for perspective)
- **youtube** → creator insights, visual trends (cite for viewpoint)
- **x** → operator hot-takes, expert opinions (cite for expert perspective)
- **instagram** → cultural patterns (cite for trend context)

This prevents the script from citing a Reddit comment as evidence for a market statistic, or a tweet as proof of a research finding.

### Layer 5 — Prompt Disciplines

- "Reject anything that smells stale"
- "Skip SEO listicles and vendor blogs"
- "No 'Ultimate Guide' / 'X Things You' template phrasing"
- Every URL must be cited verbatim from tool output — never invented

### Layer 6 — Tiered Verification

Claims are verified against the **appropriate** source platform — not all sources equally. A statistic is verified against web articles; an attributed quote is verified by the social post itself. This prevents the system from marking claims as "unverifiable" when the evidence exists on the wrong platform type. See Fact-Checking section below for full tiering rules.

---

## Fact-Checking (Verification Layer)

Runs AFTER content generation. A direct LLM structured-output call at each pipeline stage — NOT a CrewAI agent (~5× cheaper in tokens, ~3× faster). Code: `backend/app/services/fact_checker.py`, WebSocket wrappers: `backend/app/agents/verifier/service.py`.

### Stage A — Claim Extraction & Triage (1 LLM call)

The system does **not** extract every numeric claim from the text. It applies a **two-question triage test** to every candidate:

1. Would the script be *materially wrong* if this number was incorrect?
2. Is this claim presented as a *definitive fact* (not an example or estimate)?

Only **YES+YES** claims are classified as **"core"** and proceed to verification. Everything else is **"contextual"** — skipped entirely.

| Classification | Example | Action |
|---|---|---|
| **core** | "73% of startups fail within 5 years" — central statistical assertion | Verified against sources |
| **core** | "McKinsey reports AI adoption grew 60%" — named-source finding | Verified against sources |
| **contextual** | "You pay fifty bucks a month for Game Pass" — illustrative price example | Skipped |
| **contextual** | "Imagine running fourteen different SaaS tools" — hypothetical | Skipped |
| **contextual** | "It takes about five minutes to set up" — rough estimate | Skipped |

The extraction prompt (`_EXTRACT_SYSTEM`) uses explicit in-context examples of what to skip — not abstract rules. The LLM learns from concrete counter-examples.

### Stage B — Tiered Source Verification (1 LLM call)

Only **core** claims are verified. The LLM applies **different evidence standards per claim type** — a statistic needs a web source, but an attributed quote can be verified by the social post itself.

**Claim type → Evidence standard:**

| Claim Type | Required Evidence | Example |
|---|---|---|
| `statistic` | Web source with matching numbers | "73% fail" needs a web article with that stat |
| `market_assertion` | Web source confirming the market claim | "$50B market" needs a market report |
| `historical_fact` | Web source confirming the event | "Apple launched the iPhone in 2007" |
| `attributed_quote` | The named source exists and said it | "@expert argues X" — the tweet IS the evidence |
| `definitional` | Any relevant source (low bar) | Common knowledge, industry definitions |
| `other` | Best effort against any source | — |

**Source platform → What it can verify:**

| Platform | Can Verify | Cannot Verify |
|---|---|---|
| `web` | Statistics, market data, historical facts | — |
| `reddit` | Community sentiment, user experiences | Statistics (a Reddit comment with a number isn't verification of that number) |
| `youtube` | Creator statements, visual trends | Market data |
| `x` | Individual opinions, expert statements | Statistics |
| `instagram` | Cultural patterns, visual trends | Statistics |

Verdicts:

| Verdict | Meaning | Example |
|---|---|---|
| `verified` | Source confirms claim using the right evidence standard | "73% fail" matches web article "7 out of 10 don't survive" |
| `contradicted` | Source directly contradicts the claim | Source says 40% when script claims 73% |
| `unverifiable` | No appropriate source covers this claim | Statistic only found in Reddit comments, not web sources |

**Smart matching rules**:
- Semantic equivalence: "73% of companies fail" matches "7 out of 10 startups don't survive"
- Rounding tolerance: "73%" matches "about 70%" or "roughly three quarters"
- Same ballpark: "$50B market" matches "market valued at $48 billion"
- For `attributed_quote`: the source URL + matching author is verification — exact quote text not required

### Stage C — Exa Fallback

If a core claim is unverifiable against existing sources AND `EXA_API_KEY` is set, the system runs parallel Exa web searches (one per claim, 3 results each) and re-verifies. This catches claims the research phase missed.

### The 4 Checkpoints

**Checkpoint 1 — Ideas → Research Sources**
Runs after ideas are generated. Extracts core claims from each idea's `rationale` and `why_now`, verifies against the SourceRefs captured by Agent 1.

**Checkpoint 2 — Script → Research Sources**
Runs after the script is generated. Reads `research_snapshot.sources` from the idea's persisted JSONB. Extracts claims from all `talking_points`. A typical 5-section script with 25+ talking points might contain 15+ numeric references — but only 2-4 are "core" claims that need verification. The rest are illustrative examples and rough estimates.

**Checkpoint 3 — Scene Text → Script (Cross-Check)**
Runs after the scene is built. Extracts all text from scene elements and cross-checks against the approved script. Flags:
- `new_claim` — scene element introduces a statistic not in the script (hallucination risk)
- `mismatch` — scene element contradicts a script talking point
- `missing_context` — scene text is too terse but looks suspicious

This checks against the *script as source of truth* — the script was already verified at Checkpoint 2, so the scene must not introduce new unverified claims.

**Checkpoint 4 — Scene Structure → Outline**
Deterministic check (no LLM). Matches outline item frame numbers against scene element `groupIds`. Flags empty frames and scenes with < 3 elements.

### UI Presentation

- Summary bar shows verified count and contradicted count. Unverifiable shown as "could not verify" in neutral gray — NOT as a failure metric
- Core claim cards: expandable with source URL, evidence text, confidence %, and explanation
- Contextual claims: collapsed under "N illustrative references (not fact-checked)"
- Scene verification: separate layout for cross-check issues and structure issues

### Verification Event Protocol

```
verifier_start              → verification starting (stage: ideas|script|scene)
verifier_claim_check        → progress: count, checked
verifier_search             → running Exa queries for unmatched core claims
ideas_verification_ready    → Checkpoint 1 report
script_verification_ready   → Checkpoint 2 report
scene_verification_ready    → Checkpoints 3+4 report
```
