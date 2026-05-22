# Research Agent Rebuild — Engineering Brief
For: Priyanshu (LadderFlow), Firdosh (Ladder Brief) From: Shiv Date: May 2026 Companion document: Production Unified Research Agent for Personal-Brand Content: 2026 Architecture Report (research report, attached separately — read this brief first, then the report for depth)

## TL;DR
We’re consolidating LadderFlow and Ladder Brief onto a single, shared research agent. Both products will hit the same agent over a clean interface; what differs between products is only the output adaptation layer (LadderFlow → podcast outline + voice prompts; Ladder Brief → canvas-ready video outline). The research agent itself is one codebase, one cost center, one eval harness.
Why: research is the upstream choke point for both products. If research is great, downstream outputs are great. If research is mid, no amount of voice-agent polish or canvas UX saves the output. Ladder Brief’s current research pipeline is significantly closer to production-grade than LadderFlow’s, and Firdosh has done good work on it. We’re going to take that pipeline as the base, harden it, add the layers it’s missing (comment mining, supply-side analysis, defendable thesis pass), and then plug both products into it.
Ownership: - Firdosh owns the unified research agent. The Ladder Brief pipeline is the foundation; Firdosh has the most context on it and the strongest design decisions are already there. Target: wrap this week. - Priyanshu owns LadderFlow v2.0 — this week he locks the Content Posting PRD for v2.0 in parallel with Firdosh’s build. Once the unified agent ships, Priyanshu integrates LadderFlow with it. He consumes the research agent via a clean interface; he doesn’t need to become a research-agent expert, but he does need to understand the contract.
This brief tells each of you what to do, in what order, and how we’ll measure success. Read all of it (yes, including the other person’s section) so you understand the full system.

## Part 1: Where things stand today
### LadderFlow (Priyanshu)
Current research pipeline: - Perplexity Sonar (depth pass) + Tavily (breadth pass) in parallel - Merged brief → Claude Sonnet 4.6 extracts 4 angles (Strategy / Signal / Execution / Contrarian) - User picks an angle → drives podcast outline + voice interview
Honest assessment: This is a competent v1 but architecturally thin. It’s a search agent dressed up as a research agent. The 4-angle extraction is genuinely good — that survives. Everything underneath it is replaceable. Specifically:
No native pull from Reddit / YouTube / X / HN — you’re trusting Perplexity to surface community sentiment, and it doesn’t, reliably.
No supply-side analysis — you don’t know what already exists on the topic or whether it’s any good.
No creator-specific filtering — Greg Eisenberg and a fintech operator asking about “AI agents” get the same 4 angles.
No demand validation — Claude is inferring what people want from a Perplexity summary. Guess on top of a guess.
This isn’t a criticism of the engineering — it’s a reflection of where LadderFlow was in its lifecycle. The MVP needed to ship; this got it shipped. Now we’re past that.
### Ladder Brief (Firdosh)
Current research system: - 3 sequential agents (Trend Researcher → Outlier Scorer → Idea Architect) - Trend Researcher fires 6 tools in parallel: Exa web search, ScrapeCreators for Reddit search + Reddit trending + YouTube trending + X user tweets + Instagram reels - Quality gates at the tool layer (engagement thresholds, freshness windows) - Outlier Scorer: cross-platform corroboration (+10 if signal on 2+ platforms), KG gap detection (+5 if fills a gap), rejects generic takes (<30 score dropped) - Idea Architect: 4–6 video idea drafts with title, rationale, why_now, opportunity_score, outlier_score, suggested_tags - Tiered fact-checking (claim type → evidence platform → smart matching rules) - 4 verification checkpoints across the pipeline
Honest assessment: This is meaningfully sophisticated. The decisions worth keeping: - Multi-platform parallel signal collection ✓ - Quality gates filtering at the tool layer (not the LLM layer) ✓ - Cross-platform corroboration as the core scoring signal ✓ - Knowledge-graph gap detection ✓ - Generic/recycled takes explicitly rejected ✓ - Tiered fact-checking with platform-aware verification ✓ - Two-question triage on what’s actually a “core claim” ✓
What’s still missing: - No comment mining — pulls posts but not the comments on those posts, where the “I wish you’d covered X” gold actually lives - No People Also Ask / search autocomplete (cheap, high-signal, missing) - The 6 video drafts surface but aren’t synthesized into a thesis (“make THIS, because the existing top 3 videos miss X”) - No timing/news layer — 90-day Exa filter is freshness, not urgency - No explicit supply-side quality assessment — surfaces top videos but doesn’t ask “are they actually good?”
### What we’re building
A unified research agent that combines what’s working in Ladder Brief with the LadderFlow angle-extraction layer, plus the gaps both pipelines share. Architecturally, six layers:
Demand-side signals — multi-platform parallel pull + comment mining + PAA
Supply-side analysis — top content quality, gap detection
Creator-specific filtering — knowledge graph cross-ref
Outlier scoring — cross-platform corroboration
Synthesis — narrative pass + thesis generation
Strategic angle extraction — 4-lens model from LadderFlow
Then verification (Ladder Brief’s tiered fact-checking, already excellent).
The two products diverge only at the output adaptation layer: - LadderFlow → angle → podcast outline + voice prompts - Ladder Brief → angle → canvas-ready outline with talking points

## Part 2: Target architecture (shared spec)
### The pattern
We use orchestrator-subagent with a shared filesystem artifact. This is the pattern Anthropic published in June 2025 and has refined through subsequent posts (the April 2026 Planner / Generator / Evaluator post; the harness engineering post on long-running agents). It’s also what LangGraph’s Deep Agents (Jan 2026) and Open Deep Research now default to.
Mechanically: - A Lead/Planner agent decomposes the brief into independent sub-tasks - Subagents run in parallel, each with its own clean context window, each running its own tool loop - Subagents write findings to a shared filesystem (Postgres + object storage in our case) — not back through chat - The Lead reads pointers and synthesizes - An Evaluator agent runs critique-refine cycles on the synthesis output (this is where the thesis pass lives)
Why this pattern, not “one big agent with all the tools”: - Context isolation — Anthropic and LangChain have both published on “context rot”: as a single context window fills past ~150K tokens, instruction-following degrades meaningfully. Keeping each subagent under 30K context is the cheap win. - Parallelism — 6 subagents in parallel = 4–6× faster wall-clock vs. sequential. This matters for product UX. - Independent failures — one subagent timing out on Reddit doesn’t kill the whole run.
Trade-off worth naming: Anthropic publicly reports multi-agent systems use ~15× more tokens than a single chat call. We accept that cost because for our task (breadth-first research with parallel-decomposable sub-tasks), the parallelism buys us speed and quality that justify the spend. We mitigate the multiplier with prompt caching, embedding-based pre-filtering, and routing cheap-model summarization vs. frontier-model synthesis — see the cost section.
### The six layers
#### Layer 1: Demand-side signals
What it does: Parallel pull from every place where audience demand leaks out.
Subagents (run in parallel): - WebSearchAgent — Tavily (breadth) + Exa (semantic depth). 10–15 queries per run. - RedditAgent — ScrapeCreators or Apify Reddit Scraper. Posts + comment trees (this is new). Sort by top for received wisdom, controversial for objections, search-by-date for emerging. - YouTubeAgent — YT Data API for video metadata (free, 10K units/day), then either yt-dlp getcomments=True (free, fragile) or Apify YouTube Comments Scraper at $0.50/1K comments (fast, reliable). Comments are the gold. - HackerNewsAgent — Algolia HN API (free, 10K req/hr, no key required). For technical and B2B/founder topics this is the highest-signal-per-dollar source we have. Currently underused. - PAAAgent — DataForSEO Standard ($0.60/1K) or Serper ($0.30–$1/1K) for People Also Ask + autocomplete. Cheap, high-signal, currently missing from both pipelines. - TwitterAgent — deferred. We’re skipping X for v1. Cost-to-signal is the worst of the platforms (X Pay-Per-Use $0.005/post read with 2M/mo cap; TwitterAPI.io ~$0.01/1K reads but reliability is mixed). We’ll add this in v2 if eval shows we need it. - LinkedInAgent — not building. LinkedIn comment mining is effectively dead post-Proxycurl (Proxycurl shut down July 2025 after the Jan 2025 LinkedIn lawsuit). LinkedIn is an output surface, not a research source. We respect this.
Each agent emits structured SourceRef objects (title, URL, snippet, engagement metadata, platform tag) into the shared artifact filesystem. Quality gates run inside each tool, not in the LLM — bad data never enters the context window. Keep Firdosh’s existing thresholds (Reddit ≥10 score / ≤28 days, YouTube ≥5K views / ≤90 days, etc.) as the starting point.
Comment mining specifically: for each top post/video the agent surfaces, it pulls the top 50 comments by engagement. We embed every comment with text-embedding-3-small ($0.02/1M tokens, basically free) and cluster. The cluster centroids that match templates like “I wish you covered X” / “I came here for Y but didn’t find it” / “still don’t understand Z” are surfaced to the synthesis layer as unmet asks. This is the single biggest signal-quality improvement we can make.
#### Layer 2: Supply-side analysis
What it does: For each candidate topic, asks “what already exists, and how good is it?”
Mechanically: - Pull top 10 videos for the query (YT Data API) - Compute engagement-to-view ratios (likes/views, comments/views) — proxies for retention since true retention is private - Sentiment-classify the comments. Negative-disappointed sentiment despite high views = audience-disappointment signal = gap. - Recency check: top videos older than 18 months on a fast-moving topic = automatic gap. - Format gap: if all top videos are 20-min long-form on a topic where the audience is watching Shorts, that’s a packaging gap. - Depth gap: comment complexity vs. video length — sophisticated comments on shallow videos = “make the deep version” opportunity.
Output: a SupplySideReport with gap_type, confidence, evidence_urls, gap_description. Feeds into the synthesis layer as constraints on the thesis.
#### Layer 3: Creator-specific filtering (knowledge graph)
What it does: Filters demand-side signals through the user’s KG.
You both already have KGs in your respective products. The unified agent expects a standard KG interface:
class CreatorKG:
    def get_user_context(self, user_id: str) -> dict:
        """Returns: niche tags, past topics covered, audience description, voice/tone descriptors."""
    def gap_score(self, topic: str, user_id: str) -> float:
        """Returns 0–1 — how much this topic fills a gap in the creator's existing coverage."""
    def saturation_score(self, topic: str, user_id: str) -> float:
        """Returns 0–1 — how much the user has already covered this topic."""
Two scoring rules to bake in (these are non-obvious and matter): - Rank-up topics that fill gaps (Firdosh, you already do this — keep it) - Rank-DOWN topics where 5+ creators bigger than the user already dominate, even if signal is high. This is the “blue ocean” filter. A creator at 0 followers writing about RAG eval is going to lose to creators with 50K followers writing the same thing. Don’t surface that topic — surface its niche cousin where the supply is thinner.
The “starting from zero” persona is non-negotiable here. If the agent works for someone at 0 followers, it works for everyone. The reverse isn’t true.
#### Layer 4: Outlier scoring with cross-platform corroboration
What it does: Combines all signals into a single score per candidate topic.
The formula (this generalizes Firdosh’s existing scorer):
TrendScore(topic) = 
    w₁ - velocity(topic, 7d) / baseline(topic, 90d)        // demand growth
  + w₂ - engagement_quality(topic)                         // not just views
  + w₃ - platform_count_with_signal(topic)                 // ≥2 platforms required
  + w₄ - KG_alignment(topic, user)                         // creator fit
  + w₅ - supply_gap_size(topic)                            // unmet demand
  - w₆ - saturation(topic)                                 // already covered well
  - w₇ - creator_size_mismatch(topic, user)                // blue-ocean filter
Hard rule: a topic must register on ≥2 platforms with positive velocity to pass Layer 4. Single-platform signals are noise more often than they’re trends.
Hand-tune w₁–w₇ on a held-out set of 30 real test topics. Don’t ship default weights. Firdosh, your existing weight table is the starting point; we’ll re-tune after Layer 1 is rebuilt.
#### Layer 5: Synthesis — thesis generation
What it does: Goes from “here’s a pile of validated topics” to “here’s the argument the user should make.”
This is the layer neither current pipeline has. It’s also where the real product moat lives. None of the existing creator tools (Spotter, Subscribr, 1of10, Castmagic) implement a real thesis pass — they generate ideas, not arguments.
Pattern (STORM-inspired, adapted): 4 perspective agents run in parallel, each producing a candidate thesis through the lens of one strategic frame:
Strategy lens — what’s the macro-narrative, the framing that recasts the topic
Signal lens — what’s the leading indicator nobody else has seen yet
Execution lens — what’s the operator-level “how to actually do this”
Contrarian lens — what’s the dominant view, and why is it wrong
Each candidate thesis = one sentence + supporting points + the supply-side rationale (“make THIS, because the existing top 3 videos miss X, Y, Z”).
A moderator agent (Co-STORM-style) scores all 4 candidates against:
score = defendability × novelty × KG_fit × supply_gap_size
and picks the strongest. The other 3 candidates are not discarded — they’re surfaced to the user as “we considered Strategy angle but rejected because…” This transparency is unique and worth keeping as a product differentiator.
#### Layer 6: Strategic angle extraction (output adaptation)
What it does: Takes the winning thesis and adapts it to the product format.
This is where the two products diverge.
For LadderFlow: thesis → podcast outline structured as opening hook + 4–6 talking sections + provocative interview questions designed to make the user riff. The voice agent uses these questions as the interview script.
For Ladder Brief: thesis → Excalidraw-ready canvas with thesis at the center, supporting points as nodes, supply-side rationale as sticky notes, transitions as edges. Renders to the canvas UI.
Both products consume the same WinningThesis object from the research agent. The adaptation is local to each product.
### Verification (carry over from Ladder Brief)
Firdosh’s tiered fact-checking is the best layer in either current pipeline. Carry it over verbatim: - Two-question triage (would the script be materially wrong if this number was incorrect? is it presented as definitive fact?) - Tiered evidence standards per claim type (statistic → web; attributed quote → social post itself) - Smart matching rules (semantic equivalence, rounding tolerance, ballpark) - Exa fallback for unverifiable core claims - 4 checkpoints across the pipeline
This becomes the verification layer in the unified agent without modification.
### The contract between the agent and the products
The unified research agent exposes one interface:
async def run_research(
    user_id: str,
    input: ResearchInput,        # keywords | YouTube URL | newsletter URL | freeform
    knowledge_graph: CreatorKG,  # the user's KG client
    config: ResearchConfig,      # cost ceiling, timeout, lens preferences
) -> ResearchResult:
    """Returns winning thesis + 3 rejected candidates + full source provenance."""
@dataclass
class ResearchResult:
    winning_thesis: Thesis
    rejected_candidates: list[Thesis]   # 3 — Strategy/Signal/Execution/Contrarian minus winner
    sources: list[SourceRef]
    supply_side_report: SupplySideReport
    unmet_asks: list[CommentCluster]     # from Layer 1 comment mining
    cost_breakdown: CostBreakdown
    run_id: str
Priyanshu and Firdosh both consume this interface. Neither product sees the internals. If the research agent improves, both products improve simultaneously. This is the entire point of consolidating.
### Stack (concrete choices)
Orchestration: LangGraph. The CrewAI pipeline Firdosh built can be wrapped as a LangGraph node, but new work goes in LangGraph. Reasoning: LangGraph reached v1.0 in late 2025 and is now the default LangChain runtime; v1.1.3 (March 2026) added deep agent templates and distributed runtime; LangSmith tracing is materially better than CrewAI’s debugging story for multi-agent failures. CrewAI is fine for prototyping but teams hit a ceiling on it 6–12 months in — we’re past that point.
Models (May 2026 pricing): - Synthesis + thesis: Claude Sonnet 4.6 ($3/$15 per 1M tokens). Default to Sonnet, escalate to Opus 4.7 ($5/$25) only if eval shows the quality gap is real. Sonnet at 1M context with 90% prompt caching is the production sweet spot. - Map-reduce summarization (per source): Claude Haiku 4.5 ($1/$5) or GPT-5 Mini ($0.25/$2). GPT-5 Mini is cheaper; use it unless tooling integration is harder than it’s worth. - Filtering / classification / dedup: Gemini 2.5 Flash-Lite ($0.10/$0.40) or GPT-5 Nano ($0.05/$0.40). Embarrassingly cheap. - Embeddings: OpenAI text-embedding-3-small ($0.02/1M tokens). Use everywhere.
Search/scraping: - Web: Tavily + Exa (already in use, keep) - PAA: DataForSEO Standard ($0.60/1K) - Reddit: ScrapeCreators (already in use, keep) — confirm post comments endpoint coverage - YouTube data: YT Data API (free) for metadata; Apify YouTube Comments Scraper ($0.50/1K) for comments - HN: Algolia API (free) — Firdosh, please add this; it’s $0 and high-signal - LinkedIn / Twitter: not building for v1
Storage: - Postgres (existing) for run metadata, source refs, KG - pgvector (existing) for embeddings - S3 or equivalent for the per-run artifact filesystem - Redis for prompt-caching and search-result caching with 24–72h TTLs (search-intent and comment corpora are stable on this timescale)
Observability: - LangSmith for traces (non-negotiable for debugging multi-agent failures) - A simple cost-per-run dashboard in our existing stack — see Cost Monitoring section

## Part 3: Individual instructions
### For Firdosh — owner of the unified research agent
All four phases below to be wrapped within this week. The phases are a sequencing guide (do them in order), not a multi-week timeline. Move fast; the architecture work matters more than perfect polish on any one layer — we’ll iterate after.
Phase 1: collapse onto the unified spec.
Stand up the LangGraph skeleton with the Lead/Subagent pattern. Use the LangGraph Deep Agents template as the starting point — do not build the orchestration loop from scratch. The template handles filesystem-as-artifact, planning tool, and subagent delegation.
Wrap your existing CrewAI pipeline as a single LangGraph node. This is the bridge — it keeps the existing pipeline functional while you swap pieces underneath.
Define the ResearchResult interface and the CreatorKG interface (specs above). Get sign-off from Priyanshu before you finalize — he needs to consume this from LadderFlow.
Migrate Layer 4 (your existing scorer) and the verification layer (your existing fact-checker) into the new graph as nodes. These are the two pieces that already work; don’t rewrite them.
Phase 2: comment mining + PAA.
Add the comment mining subagent for Reddit and YouTube. This is the highest-leverage feature in this rebuild. Mechanics:
For each top post/video Layer 1 surfaces, fetch top 50 comments by engagement.
Embed every comment with text-embedding-3-small.
Cluster (HDBSCAN or simple k-means on cosine distance, k=8 is fine to start).
Match cluster centroids against template prompts (“I wish you covered X”, “I came here for Y but didn’t find it”, “still don’t understand Z”, “the part about W is wrong”). Use Haiku 4.5 for the matching — it’s cheap and the task is simple.
Output: CommentCluster objects with theme, representative_comments, frequency, sentiment, unmet_ask boolean.
Add the PAAAgent (DataForSEO Standard). Pull PAA + autocomplete once per topic. Cache results for 72h (this stuff doesn’t move on shorter timescales). Embed and pass top-15 by similarity to the brief.
Add the HackerNewsAgent (Algolia API). Free. High-signal for technical/B2B/founder topics — exactly Shiv’s niche. There’s no excuse to skip this; takes a day to build.
Phase 3: supply-side and synthesis.
Build Layer 2 (supply-side analysis). For each candidate topic, pull top 10 videos via YT Data API, compute engagement ratios, sentiment-classify comments, output SupplySideReport.
Build Layer 5 (synthesis with 4-lens thesis pass). This is the differentiator — spend time on it. The four perspective agents run in parallel, the moderator agent picks the winner, all four are surfaced to the user. STORM’s OutlineGenerationModule is a useful reference; we’re not implementing STORM directly, but the pattern of “perspectives produce candidates, moderator picks” is exactly what we want.
Hand-tune Layer 4 weights against 30 real test topics from Shiv’s content history. The weights you have today are a v0; we re-tune once everything else is in place.
Phase 4: hardening.
Add prompt caching everywhere there’s a stable system prompt (90% input cost discount on cache hits, 1024-token min prefix on Anthropic, 5-min default TTL with 1-hour available).
Implement embedding pre-filter before any LLM synthesis call — top-k by cosine to brief + each lens prompt. This drops downstream LLM cost by 5–10×.
Implement budget-aware routing — if cheap signals (HN, PAA cache, KG retrieval) surface ≥10 high-relevance items per lens, skip the expensive signals (paid Reddit/YouTube scraping). Simple rule, big cost lever.
Set up the eval harness — see the Eval Setup section below. Don’t ship a Layer-X change without re-running eval.
Decision points where you ping Shiv: - Before finalizing the ResearchResult interface (Phase 1) - After Layer 5 thesis pass produces first end-to-end output — Shiv needs to taste-test it before we commit to the synthesis approach - Before turning on Twitter/X integration (we’re deferring v1; revisit if eval shows we need it)
### For Priyanshu — owner of LadderFlow product layer
While Firdosh is finalising the unified research agent this week, your focus is the Content Posting PRD for LadderFlow v2.0. Most of the LadderFlow product layer is already built — voice agent, transcript handling, basic post generation. What’s missing is the spec for the content posting flow that v2.0 needs.
Phase 1: Content Posting PRD for LadderFlow v2.0.
Write a complete PRD covering the content posting flow end-to-end. At minimum it should cover:
The user journey from end-of-podcast to published post — what happens between the user clicking “end interview” and a post going live on LinkedIn. Every step, every state, every error path.
Post generation logic — how the transcript becomes 3–5 standalone insights, how each insight becomes a post draft, how voice/tone is preserved, how supporting evidence from the research agent is surfaced.
User review and editing UX — what the user sees, what they can edit, how edits feed back into the system (do we learn from them? store them as voice samples?).
Scheduling and publishing — direct LinkedIn posting vs. queue vs. draft handoff. API integration, OAuth, rate limits, failure modes.
Feedback loop — track which posts get published, which get edited heavily, which get discarded. This is the only metric that tells us if the agent is actually good.
Edge cases — what happens if the transcript is too short, too long, the user rambled, the audio cut out, the LinkedIn token expired, etc.
The PRD should be detailed enough that another engineer could implement from it without asking you questions. Use the same PRD format you’ve used for previous Ladder Automation work — Shiv will review and sign off before you start building.
Phase 2: deferred — wait for Firdosh.
Don’t start integration work until Firdosh’s unified research agent is wrapped. Trying to integrate against a moving interface will cost both of you time.
Phase 3: integrate LadderFlow with the unified research agent.
Once Firdosh has shipped the unified agent:
Read the final ResearchResult interface spec — that’s your contract.
Replace LadderFlow’s current Perplexity+Tavily research pipeline with a single call to the unified agent. The angle extraction you’re doing today happens inside the unified agent now (Layers 5/6); your job becomes “consume the winning thesis.”
Map the WinningThesis object into LadderFlow’s existing podcast outline + voice agent script generation. Most of the downstream pipeline doesn’t change — the input does.
Run the eval harness against LadderFlow’s specific output to confirm no quality regression after the swap.
Decision points where you ping Shiv: - Before finalising the v2.0 PRD scope (do this early — easier to course-correct on scope than on a finished doc) - After the first end-to-end test run with the unified research agent in Phase 3 - If anything in Firdosh’s ResearchResult interface doesn’t fit what LadderFlow needs — raise it with Firdosh directly before he locks the spec

## Part 4: Migration plan
We can’t break the live products during this rebuild. The migration is staged.
Stage 0: Both products keep running on current pipelines. No user-facing changes. Firdosh wraps the unified agent this week. Priyanshu finalises the v2.0 PRD in parallel.
Stage 1: Unified agent runs in shadow mode. When a user triggers research in either product, both pipelines run — the existing one (serves the user) and the unified one (results logged but not shown). Compare outputs side by side for at least a few days of real traffic before promoting.
Stage 2: Ladder Brief migrates first. Firdosh’s product is closer to the new pipeline architecturally; the migration is shorter. Switch Ladder Brief to the unified agent. Keep the old pipeline as a 24-hour rollback option.
Stage 3: LadderFlow migrates. Once Ladder Brief has been live on the unified agent and shadow-mode comparison shows no quality regression, Priyanshu switches LadderFlow over.
Stage 4: Decommission the old pipelines. Only after both products have been on the unified agent without a rollback for long enough to be confident — call it 2 weeks of stable production traffic, minimum.
Rollback criteria (any of these triggers a rollback): - Cost-per-run >2× the legacy pipeline at equivalent quality - Eval score drops below the legacy pipeline’s baseline - User-reported quality complaints spike (track this in product analytics) - p95 latency >5 minutes per run
Branch strategy: unified-research-agent long-lived branch, rebased onto main regularly. Feature flags gate the cutover per product.

## Part 5: Eval setup
Without eval, “the new research agent is better” is a vibe, not a measurement. This is non-negotiable.
### The eval set
30 representative topics from Shiv’s content history, hand-curated. For each topic, we capture: - The user’s KG context (frozen snapshot) - The “right” thesis (Shiv’s judgment, captured before the eval runs) - The “right” supporting points - Topics to avoid (saturation flags, blue-ocean violations)
This is the gold standard. It’s small, it’s hand-curated, and it’s the only thing that matters.
### Metrics
Quantitative (automated): - Coverage — fraction of “right” supporting points the agent surfaced - Precision — fraction of agent-surfaced points that are actually high-signal (vs. noise) - Cross-platform corroboration rate — fraction of high-confidence findings supported on ≥2 platforms - KG saturation false-positive rate — fraction of “topics to avoid” the agent correctly avoided - Cost per run (average, p95) - Latency per run (average, p95)
Qualitative (human eval): - Thesis defendability — Shiv rates 1–5: “would I publicly argue this?” - Thesis novelty — Shiv rates 1–5: “have I or others said this before?” - Supply-side accuracy — when the agent says “the existing top 3 videos miss X,” does it actually? - Voice/tone fit (LadderFlow only) — does the resulting LinkedIn post sound like Shiv?
Run the full eval before any architectural change ships. Run a subset (5 topics) on every PR. If a PR drops average score on the subset, it doesn’t merge.
### Implementation
LangSmith for trace capture and dataset management — this is exactly what it’s built for. Don’t roll our own. The eval dataset lives as a LangSmith dataset; eval runs trigger from CI.
For the qualitative human-eval step, build a tiny internal tool that lets Shiv (and Firdosh/Priyanshu when needed) rate outputs on a 5-point scale per dimension. 30 topics × 4 dimensions × 5 minutes = 10 hours of human time per full eval run, which is fine for shipping cadence (we’re not doing this daily).

## Part 6: Cost monitoring
Per-run cost target: $0.70–$1.20 end-to-end (search APIs + scraping + LLM synthesis + verification). If you’re consistently above $1.50, the bottleneck is almost always synthesis-stage frontier-model calls — push more into the cheap-model map step.
### Instrumentation
Every run emits a CostBreakdown:
@dataclass
class CostBreakdown:
    run_id: str
    layer_costs: dict[str, float]   # per-layer dollar cost
    tool_costs: dict[str, float]    # per-tool dollar cost
    model_costs: dict[str, float]   # per-model token spend
    total: float
    duration_seconds: float
This goes into a Postgres table. We build a simple dashboard (Metabase or Grafana) over it that surfaces: - Cost per run (trend, last 7/30 days) - Cost-per-run distribution (p50, p95, p99) - Cost by layer (where is the spend going?) - Cost by tool (which APIs are eating the budget?) - Cost by user/run-type (are some topics 10× more expensive than others, and why?)
### Alerting
Single run >$3 → Slack alert (something’s broken or someone’s hammering the system)
Daily spend >$50 → Slack alert (rate-limit before bills get scary)
Cost-per-run trend up >20% week-over-week → Slack alert (something regressed)
### Cost levers to pull when we’re over budget
In priority order (do them top-down until you’re back under target): 1. Add prompt caching to any system prompt + KG context block sent on every request (90% input discount on cache hits) 2. Push more summarization into Haiku 4.5 / GPT-5 Mini, reserve Sonnet 4.6 for synthesis only 3. Embedding pre-filter before any LLM call — top-k=20–50, drop downstream LLM cost 5–10× 4. Cache search and comment-corpora results 24–72h by topic+platform 5. Skip expensive signals (paid scraping) when cheap signals are sufficient (≥10 high-relevance items per lens) 6. Reduce per-source comment fetch from 50 → 25 if cluster quality holds
Last resort: drop a platform from Layer 1. We don’t want to do this — the multi-platform corroboration is the core signal — but if costs are unsustainable, the order to drop is: Instagram → Twitter (already deferred) → Reddit trending (keep Reddit search, cut trending scan) → … never drop HN (it’s free) or PAA (it’s cheap).

## Part 7: Open questions / decisions deferred
Things we explicitly haven’t decided and are okay deferring:
Twitter/X integration — deferred to v2. Revisit when eval shows we’re missing operator/expert-take signal. If/when we add it, route through TwitterAPI.io, not first-party API.
LinkedIn comment mining — not building. Legal/operational risk. LinkedIn is an output surface only.
Real-time signal layer — current pipeline catches “what’s been trending in the last 7–90 days” but not “what’s heating up this week.” Adding a faster news/Twitter layer is v2 work.
Multi-language support — English only for v1. Both products are English-first today.
Beyond podcast/video — what does this look like for Twitter threads, newsletter outlines, conference talks? Out of scope for v1; the architecture supports it (just add output adaptation layers) but we’re not building it now.

## Appendix A: 2026 updates folded in
Shiv flagged that the original research report leaned on mid-2025 references. Here’s what’s actually current as of May 2026, and what changed in the architecture:
### Anthropic engineering, post-June 2025
April 2026 — Planner/Generator/Evaluator pattern (Anthropic engineering blog). Validates the synthesis-with-evaluator approach we’re using in Layer 5 (4 perspectives + moderator = generator/evaluator separation). Anthropic reports ~10pp task-success improvement over standard prompting on complex multi-step workflows. This is the pattern, not aspirational.
March 2026 — Three workflow patterns whitepaper (sequential, parallel, evaluator-optimizer). Our architecture uses parallel (Layer 1 subagents) and evaluator-optimizer (Layer 5 thesis pass). Sequential is anti-pattern for breadth-first research.
Effective context engineering for AI agents (Anthropic, Sept 2025) and Effective harnesses for long-running agents (Anthropic, March 2026). Both validate the artifact pattern (subagents write to filesystem, return references not full content). Our shared-filesystem design comes from this.
Claude Agent SDK (productized through 2025–2026) and Managed Agents (public beta April 8, 2026, $0.08/session-hour + token costs). We’re not using Managed Agents for this — we want self-hosted control and the multi-agent coordination features are still rolling out. Reassess in 6 months.
April 2026 — Anthropic’s 2026 Agentic Coding Trends Report. Doesn’t directly apply to research agents, but the “treat context as a first-class engineered artifact” point reinforces our shared-filesystem design.
### Models (May 2026 pricing, verified)
Prompt caching: Anthropic 90% discount on cache hits, 5-min default TTL with 1-hour available. Gemini also offers ~90% on cached context. Use it.
Note: GPT-5.5 launched April 23, 2026 at $5/$30 (2× GPT-5.4 list price). We are not using GPT-5.5 — Sonnet 4.6 is meaningfully cheaper at the same tier.
### Frameworks (May 2026 state)
LangGraph v1.1.3 (March 2026) — added deep agent templates, distributed runtime in CLI. This is the version we target.
LangChain Deep Agents (Jan 2026 blog) — create_deep_agent() with built-in subagents, planning tool, and filesystem. We use this as the skeleton.
CrewAI v1.12 — added agent skills, native multi-provider support, hierarchical memory isolation. Firdosh’s current pipeline runs on CrewAI; we wrap it as a LangGraph node rather than rewrite, but new work is LangGraph.
OpenAI Agents SDK v0.13 — added MCP resource support, session persistence. Model-locked to OpenAI. Not what we’re using.
AG2 Beta (autogen redesign) — production-ready event-driven architecture. Worth knowing about; not picking it.
Pydantic AI v1.71 — added Capabilities (composable agent behavior units), AgentSpec for YAML-loaded agents, cross-provider Thinking. Useful if we want strict typing on agent state; not a primary framework choice.
### Scraping / data
ScrapeCreators — unchanged from prior assessment. Pay-as-you-go, every API included on every plan. Keep using for Reddit/YouTube/Instagram. Adrian Horning (founder) is responsive — direct contact if you hit issues.
Apify — Reddit Scraper $1/1K posts (cheaper than ScrapeCreators per-credit at scale). YouTube Comments Scraper $0.50/1K comments (the lowest-cost reliable option). Worth A/B testing against ScrapeCreators on a small sample to see which works better for our specific use cases.
Twitter/X API — Pay-Per-Use launched Feb 2026 ($0.005/post read, capped at 2M/mo). Legacy Basic ($200/mo) and Pro ($5K/mo) only available to existing subscribers. Skip for v1.
LinkedIn — closed. Proxycurl shut down July 2025. No viable comment-mining vendor. Don’t try to be clever here.
Algolia HN API — free, 10K req/hr, no key. Use it; it’s silly that we aren’t.
DataForSEO PAA — Standard $0.60/1K queries. AI Overviews now extracted from inside PAA boxes (added late 2025). Cheap, reliable, missing from both pipelines today.
### Things we’re explicitly NOT doing
Not building on Microsoft Agent Framework (GA Q1 2026). Azure-locked, smaller community, no advantage for our stack.
Not using Google ADK for orchestration. Optimized for Gemini; we want model flexibility.
Not using Bedrock Agents (managed AWS service). Locked-in. We want self-hosted.
Not adopting AGENTS.md standard. It’s emerging for coding agents; not relevant to our research-agent work.
### What I want you both to verify before locking in
Things I flagged that you should sanity-check on your end before committing implementation choices:
Apify YouTube Comments Scraper — I’m citing $0.50/1K based on the Apify listing. Verify on a real scrape that this is the actual effective cost for our access patterns (some Apify actors charge platform usage on top of result fees).
ScrapeCreators credit consumption per Reddit comment thread — Some endpoints (notably paginated comment fetches) consume more than 1 credit per call. Model your own consumption against real responses, not the homepage rule.
Claude Opus 4.7 tokenizer change — if we end up using Opus 4.7 for synthesis, run the same prompt through 4.6 and 4.7 and check the token-count delta. We may want to stay on 4.6 if the inflation is significant.
DataForSEO PAA pricing — Standard tier is $0.60/1K. Confirm the AI Overviews endpoint isn’t a separate SKU before relying on it.
LangGraph 1.1.3 breaking changes — if you’re upgrading from an earlier LangGraph version, read the migration guide. v1.0 introduced breaking changes from the 0.x line.

## Closing note
This is a real rebuild, not a refactor. Firdosh wraps the unified research agent this week; Priyanshu locks the v2.0 PRD in parallel, then integrates once the agent is shipped. The end state is a research agent that produces output a content strategist would be proud of — for someone starting from zero, not just for established creators. That’s the bar. If we hit it, both products become genuinely defensible. If we don’t, we’re shipping what every other AI content tool ships, which is fine, which is mid, which isn’t the business I want to build.
Read the companion research report for the depth on platform-by-platform feasibility, comment-mining mechanics, and the full citation trail. Come back with questions. Let’s build this properly.
— Shiv