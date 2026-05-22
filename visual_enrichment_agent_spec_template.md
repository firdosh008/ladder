# LADDER CONTENT OS Build Spec — Visual Enrichment Agent

> Image generation pipeline for Excalidraw whiteboards

**OWNER:** _  
**VERSION:** v1.0 · _  

---

## 1. Context

### What this agent does
- 
- 
- 
- 
- 
- 

### What this agent does NOT do
- 
- 
- 
- 
- 

---

## 2. Architecture

### Three-pass pipeline
- **Pass 1** — Excalidraw scene generator (existing). Outputs: _
- **Pass 2** — Visual enrichment agent (THIS DOC). Outputs: _
- **Pass 3** — Image generator + scene merger. Outputs: _

### Stack confirmation
| Layer | Choice |
|---|---|
| Orchestrator | _ |
| Storage | _ |
| API surface | _ |
| Background jobs | _ |
| Observability | _ |
| Image models | _ |

### Data flow
```
_
```

---

## 3. The Five Image Categories

### Category 1 — Concrete Noun Anchors
- **Use when:** _
- **Frequency target:** _% of total images
- **Examples:** _

### Category 2 — Metaphor Visuals
- **Use when:** _
- **Frequency target:** _% of total images
- **Examples:** _

### Category 3 — Memes / Reaction Images
- **Use when:** _
- **Frequency target:** _% of total images (hard cap: _)
- **Examples:** _

### Category 4 — Comparison / Before-After
- **Use when:** _
- **Frequency target:** _% of total images
- **Examples:** _

### Category 5 — Abstract / Mood
- **Use when:** _
- **Frequency target:** _% of total images
- **Examples:** _

### When to skip image generation entirely
- 
- 
- 
- 
- 

---

## 4. Style Worlds

- **World 1:** _
- **World 2:** _
- **World 3:** _
- **World 4:** _

| World | Concrete nouns | Metaphors | Comparison | Mood / Abstract |
|---|---|---|---|---|
| _ | _ | _ | _ | _ |
| _ | _ | _ | _ | _ |
| _ | _ | _ | _ | _ |
| _ | _ | _ | _ | _ |

> Memes bypass style worlds. Memes are always Imgflip-templated regardless of world.

---

## 5. Model Routing

### Routing matrix
| Category | Model | Mode | Resolution | Why |
|---|---|---|---|---|
| Concrete nouns | _ | _ | _ | _ |
| Metaphors | _ | _ | _ | _ |
| Memes | _ | _ | _ | _ |
| Comparison | _ | _ | _ | _ |
| Mood/Abstract | _ | _ | _ | _ |

### Cost guardrails
- Default cap: _ images per video
- Override: _
- Cache strategy: _
- Error handling: _
- Logging: _

### Model snapshot IDs (pin in production)
| Provider | Snapshot |
|---|---|
| OpenAI | _ |
| Flux | _ |
| Imgflip | _ |

---

## 6. Agent I/O Contracts

### Input contract
```json
{
  // TBD
}
```

### Output contract
```json
{
  // TBD
}
```

---

## 7. Agent System Prompt

```
_
```

### Few-shot examples

**Example 1**
- **Input:** _
- **Output:** _

**Example 2**
- **Input:** _
- **Output:** _

**Example 3**
- **Input:** _
- **Output:** _

**Example 4**
- **Input:** _
- **Output:** _

---

## 8. Curated Meme Library

### Schema
```sql
-- TBD
```

### Seed data
| Imgflip ID | Template name | Captions | When to use |
|---|---|---|---|
| _ | _ | _ | _ |

> Usage cap: agent can't use the same template ID twice in the same video.

---

## 9. Supabase Schema

### image_cache
```sql
-- TBD
```

### image_jobs
```sql
-- TBD
```

### meme_templates (seed table)
```sql
-- TBD
```

### Storage bucket
- **Bucket name:** _
- **Structure:** _
- **Public:** _
- **Max file size:** _

---

## 10. Python Reference Implementation

### Project structure
```
backend/
├── visual_enrichment/
│   ├── __init__.py
│   ├── agent.py          # _
│   ├── router.py         # _
│   ├── generators/
│   │   ├── openai_image.py  # _
│   │   ├── flux.py          # _
│   │   └── imgflip.py       # _
│   ├── scene_merger.py   # _
│   ├── cache.py          # _
│   ├── prompts.py        # _
│   └── schemas.py        # _
└── api/
    └── routes/
        └── visuals.py    # _
```

### schemas.py
```python
# TBD
```

### agent.py
```python
# TBD
```

### router.py
```python
# TBD
```

### generators/openai_image.py
```python
# TBD
```

### generators/imgflip.py
```python
# TBD
```

### cache.py
```python
# TBD
```

### scene_merger.py
```python
# TBD
```

### api/routes/visuals.py
```python
# TBD
```

---

## 11. Rollout Plan

| Phase | Days | Tasks | Acceptance |
|---|---|---|---|
| Week 1 — Foundation | 1-5 | _ | _ |
| Week 2 — Agent + Merger | 1-5 | _ | _ |
| Week 3 — Frontend + Polish | 1-5 | _ | _ |

---

## 12. Risks & Mitigations

| # | Risk | Mitigation |
|---|---|---|
| R1 | _ | _ |
| R2 | _ | _ |
| R3 | _ | _ |
| R4 | _ | _ |
| R5 | _ | _ |
| R6 | _ | _ |

---

## 13. Summary & Next Steps

### What you're building (one-liner)
_  

### Decisions already locked
- 
- 
- 
- 
- 

### Open items to confirm before kickoff
- 
- 
- 
- 

### Owner / questions
- **Build owner:** _
- **PM / decisions:** _
- **Questions:** _
