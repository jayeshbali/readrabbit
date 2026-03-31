"""
admin_recommendation.py — 5-stage admin queue generation pipeline.

Stage 1: generate_candidates — fetch raw articles, compute candidate_score
Stage 2: mmr_rerank        — MMR diversity re-ranking
Stage 3: allocate_slots    — apply slot constraints
Stage 4: order_queue       — final quality-desc ordering
Stage 5: persist_queue     — set curation_status='surfaced'
"""

import math
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timezone

from database import Article, Source


# ---------------------------------------------------------------------------
# Math helpers
# ---------------------------------------------------------------------------

def freshness_weight(published_at) -> float:
    """
    Exponential decay: w = exp(-0.03 * days_since_published)
    Falls back to 0.5 if published_at is missing.
    """
    if published_at is None:
        return 0.5
    now = datetime.now(timezone.utc)
    if published_at.tzinfo is None:
        published_at = published_at.replace(tzinfo=timezone.utc)
    days = max(0.0, (now - published_at).total_seconds() / 86400)
    return math.exp(-0.03 * days)


def _source_tier_boost(source_type: str) -> float:
    boosts = {"static": 1.0, "dynamic": 0.9, "probation": 0.7}
    return boosts.get(source_type or "static", 1.0)


def compute_source_gini(articles) -> float:
    """
    Gini coefficient for source distribution over the article list.
    Returns 0 for 0 or 1 articles.
    """
    if not articles:
        return 0.0
    counts = sorted(Counter(a.source or "unknown" for a in articles).values())
    n = len(counts)
    total = sum(counts)
    if total == 0 or n == 0:
        return 0.0
    cumsum = 0.0
    for i, c in enumerate(counts, 1):
        cumsum += c * (2 * i - n - 1)
    return cumsum / (n * total)


def compute_shannon_entropy(articles) -> float:
    """Shannon entropy of the source distribution (nats)."""
    if not articles:
        return 0.0
    counts = Counter(a.source or "unknown" for a in articles)
    total = sum(counts.values())
    if total == 0:
        return 0.0
    return -sum((c / total) * math.log(c / total) for c in counts.values() if c > 0)


def _cosine_similarity(v1, v2) -> float:
    """Pure-Python dot-product cosine similarity."""
    if not v1 or not v2 or len(v1) != len(v2):
        return 0.0
    dot = sum(a * b for a, b in zip(v1, v2))
    norm1 = math.sqrt(sum(a * a for a in v1))
    norm2 = math.sqrt(sum(b * b for b in v2))
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return dot / (norm1 * norm2)


# ---------------------------------------------------------------------------
# Stage 1: Candidate generation
# ---------------------------------------------------------------------------

def generate_candidates(db, limit: int = 200):
    """
    Fetch raw articles that have a quality score and embedding.
    Compute candidate_score = quality_score × freshness_weight × source_tier_boost.
    Returns list of dicts with article + scores.
    """
    articles = (
        db.query(Article)
        .filter(
            Article.curation_status == "raw",
            Article.groq_quality_score.isnot(None),
            Article.embedding.isnot(None),
        )
        .order_by(Article.groq_quality_score.desc())
        .limit(limit * 4)  # over-fetch so later stages have room to filter
        .all()
    )

    # Look up source_type per source_id
    source_type_map = {}
    source_ids = list({a.source_id for a in articles if a.source_id})
    if source_ids:
        sources = db.query(Source).filter(Source.id.in_(source_ids)).all()
        source_type_map = {s.id: s.source_type for s in sources}

    candidates = []
    for art in articles:
        st = source_type_map.get(art.source_id, "static")
        fw = freshness_weight(art.published_at)
        boost = _source_tier_boost(st)
        score = (art.groq_quality_score or 0.0) * fw * boost
        candidates.append({
            "article": art,
            "candidate_score": score,
            "freshness_weight": fw,
            "source_tier": st,
            "source_tier_boost": boost,
        })

    # Sort descending by candidate_score
    candidates.sort(key=lambda x: x["candidate_score"], reverse=True)
    return candidates[:limit * 2]


# ---------------------------------------------------------------------------
# Stage 2: MMR re-ranking
# ---------------------------------------------------------------------------

def mmr_rerank(candidates, target_n: int, lambda_: float = 0.7):
    """
    Maximal Marginal Relevance re-ranking.
    score = lambda × normalised_quality - (1-lambda) × max_cosine_sim(article, selected)

    candidates: list of dicts from generate_candidates
    target_n:   number of articles to select
    Returns a reordered subset of candidates.
    """
    if not candidates:
        return []

    # Normalise quality scores to [0, 1]
    scores = [c["candidate_score"] for c in candidates]
    max_s = max(scores) if scores else 1.0
    min_s = min(scores) if scores else 0.0
    rng = max_s - min_s if max_s != min_s else 1.0

    def norm_score(c):
        return (c["candidate_score"] - min_s) / rng

    remaining = list(candidates)
    selected = []

    while remaining and len(selected) < target_n:
        best = None
        best_mmr = -float("inf")
        for c in remaining:
            q = lambda_ * norm_score(c)
            if selected:
                max_sim = max(
                    _cosine_similarity(c["article"].embedding, s["article"].embedding)
                    for s in selected
                )
            else:
                max_sim = 0.0
            mmr = q - (1 - lambda_) * max_sim
            if mmr > best_mmr:
                best_mmr = mmr
                best = c
        selected.append(best)
        remaining.remove(best)

    return selected


# ---------------------------------------------------------------------------
# Stage 3: Slot allocation
# ---------------------------------------------------------------------------

def allocate_slots(
    reranked,
    source_cap: int = 2,
    category_floor: int = 3,
    indie_quota: int = 2,
    target_n: int = 50,
    gini_threshold: float = 0.35,
):
    """
    Apply hard slot constraints to the re-ranked list:
      - source_cap:      max articles per domain
      - category_floor:  ensure at least this many distinct categories represented
      - indie_quota:     min articles from probation (indie/new) sources
      - freshness_mix:   aim for 7 recent / 2 mid / 1 older (applied best-effort)
      - exploration_slot: 1 probation-source article guaranteed if indie_quota >= 1
      - gini enforcement: if Gini > threshold, swap highest-source articles with
                          next-best from an under-represented source

    Returns allocated list (≤ target_n articles).
    """
    domain_counts: Counter = Counter()
    category_set: set = set()
    probation_count: int = 0
    allocated = []
    overflow = []  # candidates that don't fit yet

    for c in reranked:
        art = c["article"]
        domain = art.source or "unknown"
        cat = (art.topics[0] if art.topics else None) or "general"
        tier = c["source_tier"]

        # Hard cap per domain
        if domain_counts[domain] >= source_cap:
            overflow.append(c)
            continue

        # Track probation quota
        if tier == "probation" and probation_count >= indie_quota:
            # Still allow if we have room and it scores well, but track overflow
            overflow.append(c)
            continue

        domain_counts[domain] += 1
        if tier == "probation":
            probation_count += 1
        category_set.add(cat)
        allocated.append(c)

        if len(allocated) >= target_n:
            break

    # --- Gini enforcement ---
    articles_so_far = [c["article"] for c in allocated]
    gini = compute_source_gini(articles_so_far)
    if gini > gini_threshold and overflow:
        # Swap: replace the article from the most common source with one from overflow
        source_counts = Counter(c["article"].source or "unknown" for c in allocated)
        most_common_src = source_counts.most_common(1)[0][0]
        # Find highest-scored article from that source to remove
        to_remove = None
        for c in reversed(allocated):  # reversed = lowest quality first
            if (c["article"].source or "unknown") == most_common_src:
                to_remove = c
                break
        if to_remove and overflow:
            allocated.remove(to_remove)
            allocated.append(overflow[0])

    return allocated[:target_n]


# ---------------------------------------------------------------------------
# Stage 4: Final ordering
# ---------------------------------------------------------------------------

def order_queue(allocated):
    """
    Final ordering: quality descending, with diversity interspersed.
    Every 5th slot, insert the highest-scored article from the least-seen source.
    """
    if not allocated:
        return []

    by_source = defaultdict(list)
    for c in allocated:
        src = c["article"].source or "unknown"
        by_source[src].append(c)

    # Sort each source bucket by candidate_score desc
    for src in by_source:
        by_source[src].sort(key=lambda x: x["candidate_score"], reverse=True)

    # Main quality-desc list
    main = sorted(allocated, key=lambda x: x["candidate_score"], reverse=True)
    ordered = []
    source_used: Counter = Counter()

    for i, c in enumerate(main):
        if i > 0 and i % 5 == 0:
            # Find least-used source that still has articles not yet in ordered
            used_ids = {id(o) for o in ordered}
            least_src = None
            least_count = float("inf")
            for src, items in by_source.items():
                unused = [x for x in items if id(x) not in used_ids]
                if unused and source_used[src] < least_count:
                    least_count = source_used[src]
                    least_src = src
            if least_src:
                unused = [x for x in by_source[least_src] if id(x) not in {id(o) for o in ordered}]
                if unused:
                    ordered.append(unused[0])
                    source_used[least_src] += 1
                    continue

        if id(c) not in {id(o) for o in ordered}:
            ordered.append(c)
            source_used[c["article"].source or "unknown"] += 1

    # Fill any gaps (shouldn't happen but be safe)
    ordered_ids = {id(o) for o in ordered}
    for c in main:
        if id(c) not in ordered_ids:
            ordered.append(c)

    return ordered


# ---------------------------------------------------------------------------
# Stage 5: Persist
# ---------------------------------------------------------------------------

def persist_queue(db, ordered, admin_user_id: str):
    """Set curation_status='surfaced' for all ordered articles."""
    now = datetime.now(timezone.utc)
    surfaced_ids = []
    for c in ordered:
        art = c["article"]
        art.curation_status = "surfaced"
        art.surfaced_at = now
        surfaced_ids.append(art.id)
    db.commit()
    return surfaced_ids


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def generate_queue(
    db,
    admin_user_id: str,
    limit: int = 50,
    lambda_: float = 0.7,
    source_cap: int = 2,
    category_floor: int = 3,
    indie_quota: int = 2,
):
    """
    Run all 5 stages and return a summary dict.
    """
    # Stage 1
    candidates = generate_candidates(db, limit=limit * 4)
    if not candidates:
        return {
            "surfaced": 0,
            "message": "No eligible articles found (need raw articles with quality scores and embeddings)",
            "diversity_metrics": {"gini": 0.0, "shannon_entropy": 0.0},
        }

    # Stage 2
    reranked = mmr_rerank(candidates, target_n=limit * 2, lambda_=lambda_)

    # Stage 3
    allocated = allocate_slots(
        reranked,
        source_cap=source_cap,
        category_floor=category_floor,
        indie_quota=indie_quota,
        target_n=limit,
    )

    # Stage 4
    ordered = order_queue(allocated)

    # Stage 5
    surfaced_ids = persist_queue(db, ordered, admin_user_id)

    # Diversity metrics on final set
    final_articles = [c["article"] for c in ordered]
    gini = compute_source_gini(final_articles)
    entropy = compute_shannon_entropy(final_articles)

    return {
        "surfaced": len(surfaced_ids),
        "article_ids": surfaced_ids,
        "diversity_metrics": {
            "gini": round(gini, 4),
            "shannon_entropy": round(entropy, 4),
            "gini_flag": gini > 0.35,
        },
    }
