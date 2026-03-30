# ReadRabbit TODOs

## After Phase 1 ships

### Create DESIGN.md with /design-consultation
**What:** Run `/design-consultation` to formalize the color system, typography, and spacing scale into a reusable design reference file (`DESIGN.md`).

**Why:** Phase 3 adds 3 new components (AdminPanel, ReviewQueue, ForYou tab). Without a design system source of truth, they will drift visually. The existing tokens are documented in the Phase 3 design doc but need to be formalized so `/design-review` and `/plan-design-review` can calibrate against them.

**Pros:** Single source of truth for all future UI work. Prevents visual drift across Phase 3 components. Makes `/design-review` and `/plan-design-review` more accurate.

**Cons:** Takes ~30 minutes. Not urgent until after Phase 3A ships and the admin panel patterns are established.

**Context:** Inferred tokens documented in Phase 3 design doc (`~/.gstack/projects/jayeshbali-readrabbit/jayeshjatinder.bali-main-design-20260328-191512.md`) under "Existing Design Tokens". Use that as the starting point. Key constraints: Inter font, #f9fafb background, no colored circles or decorative left-borders, numbers-as-design for eval metrics.

**Depends on:** Phase 3A implementation complete (so DESIGN.md reflects the final state of admin panel components).

---

### Add LLM API cost logging
**What:** After each `enrich_article()` call, log tokens used (Groq) and embedding call (Voyage) to console/JSONL. Surface totals in `/admin/stats` endpoint.

**Why:** As corpus grows, enrichment costs accumulate. Knowing cost-per-article helps decide when to pause or optimize the pipeline.

**Pros:** Prevents surprise bills. Shows cost-awareness in portfolio showcase.

**Cons:** Minor extra code. Groq + Voyage are both free at current scale, so the urgency is low.

**Context:** Enrichment pipeline added in Phase 1. Groq `llama-3.3-70b-versatile` + Voyage `voyage-2` are both on free tiers. Cost becomes relevant if corpus grows beyond ~500 articles.

**Depends on:** Phase 1 enrichment pipeline complete.

---

### Migrate /api/recommendations from GET query param to POST body
**What:** Change `GET /api/recommendations?saved_ids=a,b,c` to `POST /api/recommendations` with body `{"saved_ids": [...]}`.

**Why:** GET query strings hit proxy/CDN length limits (~2KB). At 100 saved UUIDs the URL is ~3.7KB and may be silently truncated by some proxies. Current GET approach is safe up to ~50 saves.

**Pros:** Unlimited saves. No URL length risk.

**Cons:** Frontend changes from GET to POST. Minor work.

**Context:** Threshold: migrate when `savedArticles.length` consistently exceeds 80-100 in localStorage. Note in `App.jsx` comments when the GET call is written.

**Depends on:** Phase 1 complete.

---

### Migrate cosine similarity to pgvector when pool exceeds ~500 articles
**What:** Replace the brute-force `cosine_similarity()` loop in `get_recommendations()` with PostgreSQL's `pgvector` `<=>` operator (nearest-neighbor index scan via `ivfflat` or `hnsw`).

**Why:** Brute-force cosine over 500 articles takes <100ms and is acceptable for Phase 3. At 5,000+ articles it degrades to ~1s+ per For You request. pgvector's indexed search returns top-K in ~10ms regardless of pool size.

**Pros:** Sub-10ms For You retrieval at any scale. pgvector is already in requirements.txt — zero new dependencies.

**Cons:** Requires migration to add a vector index (`CREATE INDEX ON articles USING ivfflat (embedding vector_cosine_ops)`). Index creation on 500+ rows takes a few seconds (run as a migration, not in hot path).

**Context:** `recommendation_engine.py` has `cosine_similarity()` and `get_recommendations()`. The threshold to act is when the curated pool consistently exceeds ~500 articles and For You response time noticeably degrades. Current Phase 3 target is well under this.

**Depends on:** Phase 3B complete (For You endpoint using pool retrieval).
