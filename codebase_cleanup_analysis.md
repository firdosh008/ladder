# Ladder Content OS — Codebase Cleanup Analysis

> **Compared against:** [Ladder Content OS Final Full PRD](file:///d:/Development/Zero/ladder/ladder/Ladder%20content%20os%20final%20full%20prd.txt)
> **Analysis date:** 2026-05-04

---

## Executive Summary

After a deep read of the full PRD and every source file in both `frontend/` and `backend/`, I've identified **unnecessary code, over-engineered fallbacks, dead directories, duplicated logic, and stale probe scripts**. The codebase has grown organically around the scene-generation pipeline and carries a fair amount of weight that isn't justified by what it currently does.

Below is the full finding list, followed by a **prioritized cleanup backlog** at the end.

---

## 1. Dead / Unnecessary Directories & Files

### 🔴 Priority: HIGH — Remove immediately

| Item | Location | Why it's dead |
|------|----------|---------------|
| **`backend/excalidraw-diagram-skill-main/`** | [dir](file:///d:/Development/Zero/ladder/ladder/backend/excalidraw-diagram-skill-main) | Reference material directory (contains a `SKILL.md` and `references/`). Not imported anywhere in the codebase. Was a research artifact during the diagram skill design phase. |
| **`backend/excalidraw-skill-master/`** | [dir](file:///d:/Development/Zero/ladder/ladder/backend/excalidraw-skill-master) | Another reference archive (`CLAUDE.md`, `README.md`). Not imported or referenced by any Python module. Dead weight. |
| **`backend/app/agents/diagram/__pycache__/`** | [dir](file:///d:/Development/Zero/ladder/ladder/backend/app/agents/diagram) | Empty module directory — contains only `__pycache__/` with zero source files. The `diagram` agent concept was superseded by `scene/mcp_diagram.py`. |
| **`backend/probe_provider.py`** | [file](file:///d:/Development/Zero/ladder/ladder/backend/probe_provider.py) | One-off smoke test script. Its own docstring says "Run from backend/". Not part of any test suite or CI. |
| **`backend/probe_scrapecreators.py`** | [file](file:///d:/Development/Zero/ladder/ladder/backend/probe_scrapecreators.py) | Its docstring literally says *"Delete once the real providers land."* The real providers (`app/providers/scrapecreators.py`) are in place. |
| **`backend/vendor/mcp_excalidraw_partial_backup/`** | [dir](file:///d:/Development/Zero/ladder/ladder/backend/vendor/mcp_excalidraw_partial_backup) | A backup copy of the vendor directory. Not referenced anywhere. Pure disk waste. |
| **`frontend/src/components/make/`** | [dir](file:///d:/Development/Zero/ladder/ladder/frontend/src/components/make) | Empty directory — 0 files. `Make.tsx` page doesn't use any sub-components from here. |

---

## 2. Excessive / Unnecessary Fallback Logic

### 🔴 Priority: HIGH

#### 2a. JSON parsing fallback tower in `diagram_service.py`

[diagram_service.py](file:///d:/Development/Zero/ladder/ladder/backend/app/services/diagram_service.py)

The `_extract_json_object()` function (lines 236-280) implements a **5-layer fallback chain**:
1. Fenced code block extraction
2. Balanced brace scanning (`_balanced_json_object_slice`)
3. Greedy first-`{`-to-last-`}` slice
4. Smart quote normalization + trailing comma stripping
5. Truncated JSON salvage (`_close_truncated_json`)

The `_close_truncated_json()` function itself (lines 163-233) is a **70-line** string-aware bracket walker that tries to salvage truncated JSON by closing brackets.

**Why this is excessive:** The `max_tokens` was already bumped to 16384 (line 408), and the prompt explicitly tells the model to close the JSON properly. The salvage path fires only on `stop_reason == "max_tokens"` which is now rare. The balanced-brace parser + greedy slice would handle 99% of cases. The truncation salvager adds ~100 lines of complex, hard-to-maintain code for an edge case that should be handled by retrying with a smaller diagram instead.

> [!TIP]
> **Recommendation:** Keep `_balanced_json_object_slice` + smart quote normalization. Remove `_close_truncated_json` and the greedy `rfind('}')` fallback. If `max_tokens` truncation happens, retry with a simpler prompt or fewer elements instead of trying to salvage partial JSON.

#### 2b. Brand color resolution — triple fallback chain

[agents.py L75-224](file:///d:/Development/Zero/ladder/ladder/backend/app/routes/agents.py#L75-L224)

`_normalize_brand_hex()` handles **5 hex formats** (missing `#`, 3-digit shorthand, 8-digit with alpha, standard 6-digit, and a last-resort regex scrape for embedded hex). Then `_resolve_scene_brand_color()` chains: session `brand_color` → brands table `primary_color` → fallback `None`. The scene WS endpoint then layers: query-string hint → DB-resolved → `None`.

**Why excessive:** Brand colors are set via a validated color picker (`<input type="color">`) in the Settings page which always produces `#RRGGBB`. The `_HEX_3`, `_HEX_8`, and regex-scrape paths will never fire from the actual UI. The 3-digit and 8-digit shorthand handlers are defensive code that protects against a scenario that can't happen.

> [!TIP]
> **Recommendation:** Simplify to: validate `#RRGGBB` or `RRGGBB` (add `#` if missing), reject everything else. Drop `_HEX_3`, `_HEX_8`, and the regex scrape (~20 lines).

#### 2c. OpenAI image model mega-brancher

[scene_visual_assets.py L221-292](file:///d:/Development/Zero/ladder/ladder/backend/app/services/scene_visual_assets.py#L221-L292)

`_openai_image_generate_kwargs()` has **4 separate branches**: `dall-e-3`, `dall-e-2`, `gpt-image-*`, and a catchall "unknown model" path. Each branch has its own quality mapping, size selection, and response format logic.

**Why excessive:** The config says `OPENAI_IMAGE_MODEL = "gpt-image-2"`. DALL-E 2 support is pointless (it produces 1024×1024 max with no quality control). The "unknown model" fallback guesses at parameters. You're using exactly one model in practice.

> [!TIP]
> **Recommendation:** Keep `gpt-image-*` and `dall-e-3` branches (2 models that actually produce usable results). Remove `dall-e-2` and the unknown-model fallback. That's ~20 lines of dead code.

#### 2d. Three image placement strategies

[scene_visual_assets.py](file:///d:/Development/Zero/ladder/ladder/backend/app/services/scene_visual_assets.py)

Three separate placement algorithms:
- `_embed_bottom_strip()` — legacy strip layout
- `_scatter_rects_in_canvas()` / `_embed_scattered_in_canvas()` — collision-avoiding scatter
- `_embed_visual_images()` with frame-anchor (`_frame_anchor_image_rect`)

Plus overflow logic where scattered → strip, and frame-anchor → strip for extras.

**Why excessive:** `SCENE_IMAGE_PLACEMENT` defaults to `"frame_anchor"`. The `canvas_bottom_strip` mode is labelled "legacy" in the code itself. The scatter algorithm is only triggered when there are no planner frames (MCP canvas path).

> [!TIP]
> **Recommendation:** Keep `frame_anchor` + `scatter` (for MCP path). Remove `_embed_bottom_strip` (~65 lines) and the `SCENE_IMAGE_PLACEMENT` config toggle. If frame-anchor runs out of frames, just skip remaining images rather than building a strip.

---

## 3. Duplicated Logic

### 🟡 Priority: MEDIUM

#### 3a. `_outline_to_text()` — defined in 2 places

- [agents.py L312-316](file:///d:/Development/Zero/ladder/ladder/backend/app/routes/agents.py#L312-L316)
- [studio_sessions.py L234-240](file:///d:/Development/Zero/ladder/ladder/backend/app/routes/studio_sessions.py#L234-L240)

Identical function, copy-pasted.

> **Fix:** Extract to `app/models/db.py` or a shared `app/utils.py`.

#### 3b. `_next_artifact_version()` — defined in 3 places

- [agents.py L319-336](file:///d:/Development/Zero/ladder/ladder/backend/app/routes/agents.py#L319-L336)
- [diagram.py L55-68](file:///d:/Development/Zero/ladder/ladder/backend/app/routes/diagram.py#L55-L68)
- Inline in [studio_sessions.py L279-288](file:///d:/Development/Zero/ladder/ladder/backend/app/routes/studio_sessions.py#L279-L288) (and again at L360-369)

Same query logic, 4 copies total.

> **Fix:** Single function in a shared module, imported everywhere.

#### 3c. Scene artifact persist — defined in 2 places

- `_persist_scene_skeleton()` in [agents.py L387-417](file:///d:/Development/Zero/ladder/ladder/backend/app/routes/agents.py#L387-L417)
- `_persist_diagram_scene()` in [diagram.py L71-97](file:///d:/Development/Zero/ladder/ladder/backend/app/routes/diagram.py#L71-L97)

Virtually identical insert with minor cosmetic differences.

> **Fix:** Consolidate into one shared function.

---

## 4. Unnecessary Configuration Complexity

### 🟡 Priority: MEDIUM

[config.py](file:///d:/Development/Zero/ladder/ladder/backend/app/config.py) has **33 settings** for a product that's pre-launch with 9 users. Many are premature:

| Setting | Why unnecessary now |
|---------|-------------------|
| `SCENE_DESIGNER_STRUCTURED_OUTPUTS` | Defaulted to `False` with a comment saying it hits errors. Dead toggle. |
| `ENABLE_MCP_SCENE_DIAGRAM` | Feature flag for an alternate path. Pick one path and commit. |
| `SCENE_IMAGE_PLACEMENT` | Legacy toggle (see §2d). |
| `SCENE_IMAGE_LANDSCAPE_FOR_DIAGRAMS` | Defaults to `True`. Nobody is going to change this. |
| `SCENE_IMAGE_FRAME_GRID_COLUMNS` | Defaults to 4. Fine-tuning knob nobody touches. |
| `SCENE_PUBLISH_MAX_ENVELOPE_BYTES` | 15 MiB default with validation range up to 64 MiB. Overkill for config. |
| `EXCALIDRAW_HEADLESS_CONNECT_TIMEOUT_S` | 180 seconds default. Should just be a constant. |
| `EXCALIDRAW_CANVAS_HEALTH_WAIT_SECONDS` | 240 seconds. Another constant-as-config. |
| `DIAGRAM_MAX_ITERATIONS` | Defaults to 1. The whole iteration logic is dead weight if max=1. |

> [!TIP]
> **Recommendation:** Audit each setting. If it hasn't been changed from its default in production, convert it to a constant. Target: **reduce from 33 settings to ~18**.

---

## 5. Features in PRD But Not Implemented (Stubs / Placeholders)

### 🟢 Priority: LOW — Not cleanup, but worth noting

These are PRD features with placeholder UI but no backend wiring. They're not dead code, but they are "promise" code:

| Feature | Status |
|---------|--------|
| **Thumbnail generation** (`gen_thumbnail`) | Settings page shows "pending". No route exists. |
| **`sharpen_this` (AI chat)** | `ChatPanel.tsx` exists in studio but has no backend endpoint. |
| **YouTube integration** | Settings shows "not connected". No OAuth flow. |
| **Notion output type** | Listed in Settings → Integrations as "post-MVP". |
| **Gamma output type** | Same as Notion. |
| **NanoBanana Pro** | Listed but no API integration. |
| **Skill files** | Tab shows "No skill files yet" — upload not wired. |
| **Models tab (BYOK)** | Shows "Server-default keys are active" — just a display table. |

These aren't dead code — they're correctly implemented as stubs per the PRD build split. **Do not remove.**

---

## 6. Landing Page Components — Questionable for Internal Tool

### 🟢 Priority: LOW

The frontend has a full marketing landing page with:
- [Hero.tsx](file:///d:/Development/Zero/ladder/ladder/frontend/src/components/Hero.tsx) (8.7KB)
- [Features.tsx](file:///d:/Development/Zero/ladder/ladder/frontend/src/components/Features.tsx) (14KB)
- [CTA.tsx](file:///d:/Development/Zero/ladder/ladder/frontend/src/components/CTA.tsx) (4.6KB)
- [Workflow.tsx](file:///d:/Development/Zero/ladder/ladder/frontend/src/components/Workflow.tsx) (5.3KB)
- [Stack.tsx](file:///d:/Development/Zero/ladder/ladder/frontend/src/components/Stack.tsx) (3.9KB)
- [Footer.tsx](file:///d:/Development/Zero/ladder/ladder/frontend/src/components/Footer.tsx) (3.3KB)
- [Marquee.tsx](file:///d:/Development/Zero/ladder/ladder/frontend/src/components/Marquee.tsx) (1.1KB)
- [Nav.tsx](file:///d:/Development/Zero/ladder/ladder/frontend/src/components/Nav.tsx) (3.5KB)
- [ExcalidrawMotif.tsx](file:///d:/Development/Zero/ladder/ladder/frontend/src/components/ExcalidrawMotif.tsx) (8.8KB)
- [Landing.tsx](file:///d:/Development/Zero/ladder/ladder/frontend/src/components/Landing.tsx) (0.5KB)

That's **~53KB** of landing page components for a product the PRD says is an "internal tool first". If the landing page isn't being used for anything (no public-facing site), this is all dead weight. If you DO plan a SaaS launch landing page, keep it but move it to a separate route/build.

---

## 7. Overly Defensive Code Patterns

### 🟢 Priority: LOW

#### 7a. `_safe_send_json` — checked 15+ times
Every WebSocket endpoint wraps every `send_json` in a try/except via `_safe_send_json`. This is fine for robustness but the pattern repeats identically ~15 times in [agents.py](file:///d:/Development/Zero/ladder/ladder/backend/app/routes/agents.py). Consider a thin WebSocket wrapper class that handles this once.

#### 7b. Iteration design guidance text
`_iteration_design_guidance()` in [diagram_service.py L27-46](file:///d:/Development/Zero/ladder/ladder/backend/app/services/diagram_service.py#L27-L46) produces elaborate iteration-specific guidance text ("Redraw pass N/M: prior composition failed QA...") but `DIAGRAM_MAX_ITERATIONS` defaults to 1. The multi-iteration text (lines 37-46) is never reached.

---

## Prioritized Cleanup Backlog

| # | Task | Impact | Effort | Priority |
|---|------|--------|--------|----------|
| **1** | Delete dead directories: `excalidraw-diagram-skill-main/`, `excalidraw-skill-master/`, `agents/diagram/`, `vendor/mcp_excalidraw_partial_backup/`, `components/make/` | Removes confusion, reduces repo size | 5 min | 🔴 **P0** |
| **2** | Delete probe scripts: `probe_provider.py`, `probe_scrapecreators.py` | Removes stale one-offs | 2 min | 🔴 **P0** |
| **3** | Deduplicate `_outline_to_text()` — extract to shared module | Fixes DRY violation | 15 min | 🔴 **P0** |
| **4** | Deduplicate `_next_artifact_version()` — extract to shared module | Fixes 4-copy DRY violation | 20 min | 🔴 **P0** |
| **5** | Consolidate scene artifact persist (`_persist_scene_skeleton` + `_persist_diagram_scene`) | Removes duplicated DB logic | 20 min | 🟡 **P1** |
| **6** | Simplify `_normalize_brand_hex()` — remove 3-digit, 8-digit, and regex scrape | Removes code for impossible inputs | 15 min | 🟡 **P1** |
| **7** | Remove `_close_truncated_json()` and greedy JSON fallback | Removes 100+ lines of edge-case salvage | 20 min | 🟡 **P1** |
| **8** | Remove `dall-e-2` and unknown-model branches from `_openai_image_generate_kwargs` | Dead model support | 10 min | 🟡 **P1** |
| **9** | Remove `_embed_bottom_strip()` legacy placement + `SCENE_IMAGE_PLACEMENT` config toggle | Dead code path, ~65 lines | 20 min | 🟡 **P1** |
| **10** | Convert hardcoded-default configs to constants (see §4 table) | Reduces config surface by ~40% | 30 min | 🟡 **P1** |
| **11** | Remove `SCENE_DESIGNER_STRUCTURED_OUTPUTS` toggle and its code paths | Dead feature flag | 15 min | 🟡 **P1** |
| **12** | Resolve `ENABLE_MCP_SCENE_DIAGRAM` — pick one scene path, remove the other | Eliminates entire alternate code path | 1-2 hrs | 🟡 **P1** |
| **13** | Extract WebSocket error-handling into a helper class to reduce repetition in agents.py | Reduces boilerplate by ~40% | 45 min | 🟢 **P2** |
| **14** | Remove multi-iteration design guidance text (lines 37-46 of diagram_service.py) since max_iterations=1 | Dead code | 5 min | 🟢 **P2** |
| **15** | Evaluate landing page components — move to separate route or remove | ~53KB of potentially dead UI | 30 min | 🟢 **P2** |

---

## Estimated Total Savings

| Category | Lines/Files removed | Time to clean |
|----------|-------------------|---------------|
| Dead files/dirs | ~5 directories, 2 scripts | 10 min |
| Duplicated logic | ~80 lines across 4 files | 45 min |
| Excessive fallbacks | ~200 lines | 1 hr |
| Config simplification | ~15 settings → constants | 30 min |
| **Total** | **~300 lines, 5 dirs, net-simpler config** | **~2.5 hrs** |

> [!IMPORTANT]
> **Do P0 items first** — they're pure deletions with zero risk. P1 items require light refactoring but each is self-contained. P2 items are quality-of-life improvements for the next developer who reads this code.
