"""
ReadRabbit Recommendation Engine v2

Improvements over v1:
1. Interest Clusters - Multiple interest centers instead of one average
2. Recency Weighting - Recent saves matter more
3. Topic Diversity - Ensure variety in recommendations

Generates personalized article recommendations based on:
- User's saved articles (what they like)
- User's dismissed articles (what to avoid)
- Time-weighted interest clusters
- Topic diversity enforcement
"""

from typing import List, Dict, Optional, Tuple, Set
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from collections import defaultdict
import random
import math


# ============== Research Paper Filter ==============

RESEARCH_PAPER_INDICATORS = {
    "urls": [
        "arxiv.org", "pubmed", "springer.com", "sciencedirect.com",
        "jstor.org", "ieee.org", "acm.org", "nature.com/articles",
        "researchgate.net", "academia.edu", "ncbi.nlm.nih.gov",
        "wiley.com", "tandfonline.com", "sagepub.com",
        "/doi/", "/paper/", "/publication/"
    ],
    "sources": [
        "arxiv", "pubmed", "nature", "science", "ieee", "acm",
        "journal of", "proceedings of", "transactions on",
        "annual review", "quarterly journal"
    ],
    "title_patterns": [
        "et al.", "a study of", "an analysis of", "empirical",
        "systematic review", "meta-analysis", "randomized controlled",
        "methodology", "proceedings", "conference paper"
    ]
}


def is_research_paper(url: str, source: str = "", title: str = "") -> bool:
    """Check if an article is likely a research paper."""
    url_lower = url.lower()
    source_lower = (source or "").lower()
    title_lower = (title or "").lower()
    
    for pattern in RESEARCH_PAPER_INDICATORS["urls"]:
        if pattern in url_lower:
            return True
    
    for pattern in RESEARCH_PAPER_INDICATORS["sources"]:
        if pattern in source_lower:
            return True
    
    for pattern in RESEARCH_PAPER_INDICATORS["title_patterns"]:
        if pattern in title_lower:
            return True
    
    return False


# ============== Similarity Calculations ==============

def cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    """Calculate cosine similarity between two vectors."""
    if not vec1 or not vec2 or len(vec1) != len(vec2):
        return 0.0
    
    dot_product = sum(a * b for a, b in zip(vec1, vec2))
    magnitude1 = sum(a * a for a in vec1) ** 0.5
    magnitude2 = sum(b * b for b in vec2) ** 0.5
    
    if magnitude1 == 0 or magnitude2 == 0:
        return 0.0
    
    return dot_product / (magnitude1 * magnitude2)


# ============== Interest Cluster ==============

@dataclass
class InterestCluster:
    """Represents a cluster of related interests."""
    name: str  # Primary topic name
    topics: Set[str]  # All topics in this cluster
    embedding: List[float]  # Centroid embedding
    article_count: int  # Number of articles in cluster
    recency_weight: float  # Higher = more recent activity
    
    def __post_init__(self):
        if isinstance(self.topics, list):
            self.topics = set(self.topics)


def calculate_recency_weight(saved_at: datetime, half_life_days: int = 30) -> float:
    """
    Calculate recency weight using exponential decay.
    
    Articles saved today = 1.0
    Articles saved 30 days ago = 0.5
    Articles saved 60 days ago = 0.25
    """
    if not saved_at:
        return 0.5  # Default for articles without timestamp
    
    now = datetime.utcnow()
    
    # Handle timezone-aware datetimes
    if saved_at.tzinfo is not None:
        from datetime import timezone
        now = now.replace(tzinfo=timezone.utc)
    
    days_ago = (now - saved_at).days
    
    # Exponential decay: weight = 0.5^(days/half_life)
    weight = math.pow(0.5, days_ago / half_life_days)
    
    return max(0.1, weight)  # Minimum weight of 0.1


def cluster_by_topics(articles: List[Dict]) -> Dict[str, List[Dict]]:
    """
    Group articles by their primary topic.
    
    Simple clustering: each article goes to its first topic.
    """
    clusters = defaultdict(list)
    
    for article in articles:
        topics = article.get("topics", [])
        if topics:
            primary_topic = topics[0]
            clusters[primary_topic].append(article)
        else:
            clusters["General"].append(article)
    
    return dict(clusters)


def build_interest_clusters(articles: List[Dict]) -> List[InterestCluster]:
    """
    Build interest clusters from saved articles.
    
    Each cluster represents a distinct area of interest.
    """
    topic_groups = cluster_by_topics(articles)
    
    clusters = []
    
    for topic_name, topic_articles in topic_groups.items():
        if len(topic_articles) < 1:
            continue
        
        # Collect all topics in this cluster
        all_topics = set()
        for article in topic_articles:
            all_topics.update(article.get("topics", []))
        
        # Calculate centroid embedding
        embeddings = [a.get("embedding") for a in topic_articles if a.get("embedding")]
        if not embeddings:
            continue
        
        dim = len(embeddings[0])
        centroid = [0.0] * dim
        for emb in embeddings:
            for i, val in enumerate(emb):
                centroid[i] += val
        centroid = [val / len(embeddings) for val in centroid]
        
        # Calculate recency weight
        recency_weights = []
        for article in topic_articles:
            saved_at = article.get("saved_at") or article.get("created_at")
            if isinstance(saved_at, str):
                try:
                    saved_at = datetime.fromisoformat(saved_at.replace('Z', '+00:00'))
                except:
                    saved_at = None
            recency_weights.append(calculate_recency_weight(saved_at))
        
        avg_recency = sum(recency_weights) / len(recency_weights) if recency_weights else 0.5
        
        clusters.append(InterestCluster(
            name=topic_name,
            topics=all_topics,
            embedding=centroid,
            article_count=len(topic_articles),
            recency_weight=avg_recency
        ))
    
    # Sort by combined score
    clusters.sort(key=lambda c: c.article_count * c.recency_weight, reverse=True)
    
    return clusters


# ============== User Profile v2 ==============

@dataclass
class UserProfile:
    """Represents a user's reading preferences with multiple interest clusters."""
    clusters: List[InterestCluster]
    dismissed_embeddings: List[List[float]]
    saved_article_ids: Set[str]
    dismissed_article_ids: Set[str]
    topic_counts: Dict[str, int] = field(default_factory=dict)
    
    def get_cluster_weights(self) -> Dict[str, float]:
        """Get normalized weights for each cluster."""
        if not self.clusters:
            return {}
        
        scores = {c.name: c.article_count * c.recency_weight for c in self.clusters}
        total = sum(scores.values())
        
        if total == 0:
            return {c.name: 1.0 / len(self.clusters) for c in self.clusters}
        
        return {name: score / total for name, score in scores.items()}


def build_user_profile(
    saved_articles: List[Dict],
    dismissed_articles: List[Dict] = None,
    reading_history: List[Dict] = None,
    weight_map: Dict[str, float] = None
) -> UserProfile:
    """Build a user profile from saved/dismissed articles and reading history.

    reading_history: list of dicts with keys: article_id, action, embedding
      actions: 'clicked' (weight 1.0), 'viewed' (weight 0.5), 'dismissed' (excluded from positive signal)
    weight_map: override default action weights, e.g. {'clicked': 1.0, 'saved': 2.0, 'dismissed': -1.0}
    Backward compatible: old callers (saved_articles, dismissed_articles) work unchanged.
    """
    dismissed_articles = dismissed_articles or []
    reading_history = reading_history or []
    default_weights = {"clicked": 1.0, "viewed": 0.5, "saved": 2.0, "dismissed": -1.0}
    if weight_map:
        default_weights.update(weight_map)

    # Merge reading history positive signals into saved_articles for cluster building
    history_positives = []
    history_dismissed_embeddings = []
    seen_ids = {a.get("id") for a in saved_articles if a.get("id")}
    for entry in reading_history:
        action = entry.get("action", "")
        article_id = entry.get("article_id")
        embedding = entry.get("embedding")
        weight = default_weights.get(action, 0.0)
        if weight < 0:
            if embedding:
                history_dismissed_embeddings.append(embedding)
        elif weight > 0 and article_id and article_id not in seen_ids:
            if embedding:
                history_positives.append({
                    "id": article_id,
                    "embedding": embedding,
                    "topics": entry.get("topics") or [],
                    "_history_weight": weight,
                })
                seen_ids.add(article_id)

    all_positive = saved_articles + history_positives
    clusters = build_interest_clusters(all_positive)

    dismissed_embeddings = [
        a.get("embedding") for a in dismissed_articles if a.get("embedding")
    ] + history_dismissed_embeddings

    topic_counts = defaultdict(int)
    for article in all_positive:
        for topic in (article.get("topics") or []):
            topic_counts[topic] += 1

    saved_ids = {a.get("id") for a in saved_articles if a.get("id")}
    dismissed_ids = {a.get("id") for a in dismissed_articles if a.get("id")}
    # Also exclude history-dismissed articles from recommendations
    for entry in reading_history:
        if default_weights.get(entry.get("action", ""), 0.0) < 0 and entry.get("article_id"):
            dismissed_ids.add(entry["article_id"])

    return UserProfile(
        clusters=clusters,
        dismissed_embeddings=dismissed_embeddings,
        saved_article_ids=saved_ids,
        dismissed_article_ids=dismissed_ids,
        topic_counts=dict(topic_counts)
    )


# ============== Scoring v2 ==============

def calculate_dismissed_penalty(
    article_embedding: List[float],
    dismissed_embeddings: List[List[float]],
    threshold: float = 0.7
) -> float:
    """Calculate penalty based on similarity to dismissed articles."""
    if not dismissed_embeddings or not article_embedding:
        return 1.0
    
    max_similarity = 0.0
    for dismissed_emb in dismissed_embeddings:
        if dismissed_emb:
            sim = cosine_similarity(article_embedding, dismissed_emb)
            max_similarity = max(max_similarity, sim)
    
    if max_similarity > threshold:
        return 0.3
    elif max_similarity > 0.5:
        return 1.0 - (max_similarity - 0.5) * 0.7
    
    return 1.0


def score_article_against_cluster(
    article: Dict,
    cluster: InterestCluster,
    user_profile: UserProfile,
    for_serendipity: bool = False
) -> Tuple[float, str]:
    """Score an article against a specific interest cluster."""
    article_embedding = article.get("embedding")
    
    if not article_embedding or not cluster.embedding:
        return (0.0, "no_embedding")
    
    article_id = article.get("id")
    if article_id in user_profile.saved_article_ids:
        return (0.0, "already_saved")
    if article_id in user_profile.dismissed_article_ids:
        return (0.0, "dismissed")
    
    if is_research_paper(
        article.get("url", ""),
        article.get("source", ""),
        article.get("title", "")
    ):
        return (0.0, "research_paper")
    
    similarity = cosine_similarity(cluster.embedding, article_embedding)
    
    if for_serendipity:
        if 0.3 <= similarity <= 0.5:
            score = 1.0 - similarity
        elif similarity < 0.3:
            score = 0.3
        else:
            score = 0.2
    else:
        if similarity > 0.85:
            score = similarity * 0.5
        elif 0.5 <= similarity <= 0.85:
            score = similarity * 1.2
        else:
            score = similarity * 0.5
    
    # Apply recency weight
    score *= cluster.recency_weight
    
    # Apply dismissed penalty
    dismissed_penalty = calculate_dismissed_penalty(
        article_embedding,
        user_profile.dismissed_embeddings
    )
    score *= dismissed_penalty
    
    reason = f"cluster={cluster.name}, sim={similarity:.2f}, recency={cluster.recency_weight:.2f}"
    
    return (score, reason)


# ============== Topic Diversity ==============

def enforce_topic_diversity(
    scored_articles: List[Dict],
    max_per_topic: int = 2,
    total_count: int = 4
) -> List[Dict]:
    """Ensure recommendations are diverse across topics."""
    selected = []
    topic_counts = defaultdict(int)
    
    for article in scored_articles:
        if len(selected) >= total_count:
            break
        
        topics = article.get("topics", [])
        primary_topic = topics[0] if topics else "General"
        
        if topic_counts[primary_topic] >= max_per_topic:
            continue
        
        selected.append(article)
        topic_counts[primary_topic] += 1
    
    return selected


# ============== Main Recommendation Function v2 ==============

def get_recommendations(
    user_profile: UserProfile,
    candidate_articles: List[Dict],
    count: int = 4,
    serendipity_ratio: float = 0.5,
    max_per_topic: int = 2
) -> List[Dict]:
    """
    Get personalized recommendations using interest clusters.
    
    Algorithm:
    1. Score articles against EACH interest cluster
    2. Take best match from each cluster (proportional to cluster weight)
    3. Add serendipity picks (low similarity to ALL clusters)
    4. Enforce topic diversity
    """
    if not user_profile.clusters:
        valid_articles = [
            a for a in candidate_articles
            if not is_research_paper(a.get("url", ""), a.get("source", ""), a.get("title", ""))
            and a.get("id") not in user_profile.saved_article_ids
            and a.get("id") not in user_profile.dismissed_article_ids
        ]
        random.shuffle(valid_articles)
        return valid_articles[:count]
    
    on_topic_count = int(count * (1 - serendipity_ratio))
    serendipity_count = count - on_topic_count
    
    cluster_weights = user_profile.get_cluster_weights()
    
    # ===== ON-TOPIC =====
    cluster_recommendations = defaultdict(list)
    
    for article in candidate_articles:
        best_cluster = None
        best_score = 0
        best_reason = ""
        
        for cluster in user_profile.clusters:
            score, reason = score_article_against_cluster(
                article, cluster, user_profile, for_serendipity=False
            )
            if score > best_score:
                best_score = score
                best_cluster = cluster.name
                best_reason = reason
        
        if best_score > 0 and best_cluster:
            cluster_recommendations[best_cluster].append({
                **article,
                "recommendation_score": best_score,
                "recommendation_type": "on_topic",
                "recommendation_reason": best_reason,
                "matched_cluster": best_cluster
            })
    
    for cluster_name in cluster_recommendations:
        cluster_recommendations[cluster_name].sort(
            key=lambda x: x["recommendation_score"], reverse=True
        )
    
    on_topic_picks = []
    picks_per_cluster = {}
    
    for cluster_name, weight in cluster_weights.items():
        picks_per_cluster[cluster_name] = max(1, round(on_topic_count * weight))
    
    for cluster_name, num_picks in picks_per_cluster.items():
        available = cluster_recommendations.get(cluster_name, [])
        on_topic_picks.extend(available[:num_picks])
    
    on_topic_picks.sort(key=lambda x: x["recommendation_score"], reverse=True)
    on_topic_picks = on_topic_picks[:on_topic_count]
    
    # ===== SERENDIPITY =====
    serendipity_picks = []
    used_ids = {a.get("id") for a in on_topic_picks}
    
    for article in candidate_articles:
        if article.get("id") in used_ids:
            continue
        if article.get("id") in user_profile.saved_article_ids:
            continue
        if article.get("id") in user_profile.dismissed_article_ids:
            continue
        if is_research_paper(article.get("url", ""), article.get("source", ""), article.get("title", "")):
            continue
        
        article_embedding = article.get("embedding")
        if not article_embedding:
            continue
        
        similarities = []
        for cluster in user_profile.clusters:
            if cluster.embedding:
                sim = cosine_similarity(cluster.embedding, article_embedding)
                similarities.append(sim)
        
        if not similarities:
            continue
        
        avg_similarity = sum(similarities) / len(similarities)
        
        if 0.25 <= avg_similarity <= 0.45:
            serendipity_score = 1.0 - avg_similarity
        elif avg_similarity < 0.25:
            serendipity_score = 0.3
        else:
            serendipity_score = 0.2
        
        dismissed_penalty = calculate_dismissed_penalty(
            article_embedding,
            user_profile.dismissed_embeddings
        )
        serendipity_score *= dismissed_penalty
        
        serendipity_picks.append({
            **article,
            "recommendation_score": serendipity_score,
            "recommendation_type": "serendipity",
            "recommendation_reason": f"avg_sim={avg_similarity:.2f} (discovery)",
            "matched_cluster": None
        })
    
    serendipity_picks.sort(key=lambda x: x["recommendation_score"], reverse=True)
    serendipity_picks = serendipity_picks[:serendipity_count]
    
    # ===== COMBINE & ENFORCE DIVERSITY =====
    all_picks = on_topic_picks + serendipity_picks
    
    diverse_picks = enforce_topic_diversity(all_picks, max_per_topic=max_per_topic, total_count=count)
    
    if len(diverse_picks) < count:
        used_ids = {a.get("id") for a in diverse_picks}
        for article in all_picks:
            if len(diverse_picks) >= count:
                break
            if article.get("id") not in used_ids:
                diverse_picks.append(article)
                used_ids.add(article.get("id"))
    
    random.shuffle(diverse_picks)
    
    return diverse_picks


def get_similar_articles(
    article: Dict,
    candidate_articles: List[Dict],
    count: int = 4,
    exclude_ids: Set[str] = None
) -> List[Dict]:
    """Get articles similar to a specific article."""
    exclude_ids = exclude_ids or set()
    article_embedding = article.get("embedding")
    
    if not article_embedding:
        return []
    
    scored = []
    for candidate in candidate_articles:
        if candidate.get("id") == article.get("id"):
            continue
        if candidate.get("id") in exclude_ids:
            continue
        if is_research_paper(
            candidate.get("url", ""),
            candidate.get("source", ""),
            candidate.get("title", "")
        ):
            continue
        
        candidate_embedding = candidate.get("embedding")
        if not candidate_embedding:
            continue
        
        similarity = cosine_similarity(article_embedding, candidate_embedding)
        
        if similarity > 0.85:
            score = similarity * 0.7
        elif 0.5 <= similarity <= 0.85:
            score = similarity * 1.2
        else:
            score = similarity
        
        scored.append({
            **candidate,
            "similarity_score": similarity,
            "recommendation_score": score
        })
    
    scored.sort(key=lambda x: x["recommendation_score"], reverse=True)
    
    return enforce_topic_diversity(scored, max_per_topic=2, total_count=count)


def extract_user_interests(user_profile: UserProfile, top_n: int = 5) -> List[str]:
    """Extract top interests from user profile."""
    if not user_profile.topic_counts:
        return []
    
    sorted_topics = sorted(
        user_profile.topic_counts.items(),
        key=lambda x: x[1],
        reverse=True
    )
    
    return [topic for topic, count in sorted_topics[:top_n]]


# ============== Debug / Explain ==============

def explain_recommendations(
    recommendations: List[Dict],
    user_profile: UserProfile
) -> Dict:
    """Generate explanation for why these articles were recommended."""
    cluster_weights = user_profile.get_cluster_weights()
    
    explanation = {
        "user_interests": [
            {
                "topic": c.name,
                "weight": round(cluster_weights.get(c.name, 0), 2),
                "article_count": c.article_count,
                "recency": round(c.recency_weight, 2)
            }
            for c in user_profile.clusters[:5]
        ],
        "recommendations": [
            {
                "title": r.get("title", "")[:50],
                "type": r.get("recommendation_type", "unknown"),
                "score": round(r.get("recommendation_score", 0), 3),
                "reason": r.get("recommendation_reason", ""),
                "cluster": r.get("matched_cluster"),
                "primary_topic": (r.get("topics") or ["General"])[0]
            }
            for r in recommendations
        ],
        "diversity_check": {
            "unique_topics": len(set(
                (r.get("topics") or ["General"])[0] for r in recommendations
            )),
            "on_topic_count": len([r for r in recommendations if r.get("recommendation_type") == "on_topic"]),
            "serendipity_count": len([r for r in recommendations if r.get("recommendation_type") == "serendipity"])
        }
    }
    
    return explanation
